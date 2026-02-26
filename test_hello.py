import asyncio
from winsdk.windows.security.credentials.ui import UserConsentVerifier
from winsdk.windows.security.credentials.ui import UserConsentVerificationResult

async def verify():
    availability = await UserConsentVerifier.check_availability_async()
    print("Availability:", availability)
    
    # Needs to be called from UI thread usually, or requires an hwnd.
    try:
        result = await UserConsentVerifier.request_verification_async("LensBlock Manual Override")
        print("Result:", result)
        if result == UserConsentVerificationResult.VERIFIED:
            print("Success")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(verify())
