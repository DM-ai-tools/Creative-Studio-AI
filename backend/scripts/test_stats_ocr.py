"""Quick test for stats image OCR."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.stats_image_service import extract_stats_from_image

IMG = Path(
    r"C:\Users\Humruth\.cursor\projects\c-Users-Humruth-Desktop-CreativeStudio-AI-Code\assets"
    r"\c__Users_Humruth_AppData_Roaming_Cursor_User_workspaceStorage_89bcf60d2e21f938ef2cbf722d03bd83_images_ClickTrends_leadgen-1174a426-48d5-4ffb-adc8-2d197b2aec24.png"
)


async def main() -> None:
    if not IMG.is_file():
        print("missing", IMG)
        return
    try:
        r = await extract_stats_from_image(IMG.read_bytes(), mime_type="image/png", filename=IMG.name)
        print("OK")
        print("headline:", r.headline_stat)
        print("roas:", r.roas)
        print("lead_forms:", r.lead_forms)
        print("summary:", r.summary_for_script[:300])
    except Exception as e:
        print("FAIL", type(e).__name__, e)


if __name__ == "__main__":
    asyncio.run(main())
