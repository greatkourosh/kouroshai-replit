from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/weather", tags=["weather"])

class WeatherResponse(BaseModel):
    current: dict

@router.get("/{city}", response_model=WeatherResponse)
async def get_weather(city: str):
    """
    Simple stub. Replace with real API integration if needed.
    Returns a minimal structure expected by the bot.
    """
    if not city:
        raise HTTPException(status_code=400, detail="City required")
    # Example static response structure used by telegram_bot.py
    return {"current": {"temperature_2m": 20}}