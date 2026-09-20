# London Bae Etsy Bridge

Bridge for Etsy OAuth and listing automation.

## Railway environment variables
Set these directly in Railway:
- ETSY_KEYSTRING
- ETSY_SHARED_SECRET
- ETSY_REDIRECT_URI=https://etsy-bridge-production-1082.up.railway.app/oauth/callback
- ETSY_SCOPES=listings_r listings_w shops_r shops_w
- ETSY_SHOP_NAME=LondonBaeDesigns

Do not commit secrets to GitHub.

## Start command
uvicorn app:app --host 0.0.0.0 --port $PORT
