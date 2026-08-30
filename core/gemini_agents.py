import os
import json
import logging
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.genai.errors import APIError

logger = logging.getLogger(__name__)

class TribunalDecision(BaseModel):
    approved: bool = Field(description="True if the trade is approved, False otherwise.")
    direction: str = Field(description="LONG or SHORT. Must be None if approved is False.", default=None)
    confidence: float = Field(description="Confidence score from 0 to 100.")
    reasoning: str = Field(description="A 1-2 sentence explanation of the final decision from the Arbitrator.")
    sl_dist: float = Field(description="The distance from entry price to stop loss (e.g. 150). Return 0 if not approved.", default=0.0)
    tp_dist: float = Field(description="The distance from entry price to take profit (e.g. 300). Return 0 if not approved.", default=0.0)

class GeminiTribunal:
    """
    The LLM-powered Brain of ARES. Uses Gemini to simulate a debate between 
    a Predator, a Risk Sentinel, and an Arbitrator before making a final trade decision.
    """
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GEMINI_API_KEY not found in environment. Tribunal will default to veto.")

    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(APIError)
    )
    def _call_gemini_with_retry(self, prompt, system_instruction):
        return self.client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=TribunalDecision,
                temperature=0.1
            )
        )

    async def deliberate(self, market_state: dict) -> dict:
        if not self.client:
            return {
                'approved': False, 
                'direction': None,
                'confidence': 0.0, 
                'reasoning': "GEMINI_API_KEY is missing. System locked.",
                'sl_dist': 0.0,
                'tp_dist': 0.0,
                'log': "VETOED: GEMINI_API_KEY missing."
            }
            
        system_instruction = """
        You are the Chief Investment Officer (CIO) of a quantitative hedge fund running a strict micro-account ($50).
        You oversee a Python Algorithmic Council (7 specialized math agents) and 3 specialized Departments (Macro, Historian, OrderFlow).
        
        They have just crunched the raw market data and cast their algorithmic votes, which you will see in the 'python_council' field of the payload.
        
        Your job is to read their mathematical reasoning, understand their biases, and make the final Executive Decision.
        - If the Python Council is overly terrified of a minor drawdown but the Order Flow shows a massive whale trap we can exploit, you can OVERRIDE them and approve the trade.
        - If the Python Council mathematically approves a trade, but your LLM reasoning realizes the macro context is too dangerous, you can VETO them.
        
        Output your final reasoning summarizing why you agreed or disagreed with the Python Council.
        Calculate sl_dist (Stop Loss distance) as 1.5 * atr_1m.
        Calculate tp_dist (Take Profit distance) as 1.5 * sl_dist.
        """

        prompt = f"Analyze the following market state and determine if we execute:\n\n{json.dumps(market_state, indent=2)}"

        try:
            # We use gemini-2.5-flash for speed since it's a high-frequency system
            response = self._call_gemini_with_retry(prompt, system_instruction)
            
            result = response.parsed
            
            return {
                'approved': result.approved,
                'direction': result.direction,
                'confidence': result.confidence,
                'reasoning': result.reasoning,
                'sl_dist': result.sl_dist,
                'tp_dist': result.tp_dist,
                'log': f"{'APPROVED' if result.approved else 'VETOED'}: {result.reasoning}"
            }
            
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            return {
                'approved': False, 
                'direction': None,
                'confidence': 0.0, 
                'reasoning': f"Gemini API Error: {e}",
                'sl_dist': 0.0,
                'tp_dist': 0.0,
                'log': f"VETOED: LLM API Failure."
            }
