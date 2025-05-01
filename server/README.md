Steps to set up back end component of GRCResponder

1. In server directory, download requirements.txt file by running the following command in terminal:
   ```
   pip install -r requirements.txt
   ```
2. Update the .env file with necessary environment variables, for local testing, you will need to obtain a Google API key and set the GOOGLE_API_KEY variable in the .env file. Obtain the key from [here](https://ai.google.dev/gemini-api/docs/api-key)
   https://developers.google.com/maps/documentation/geocoding/get-api-key
   
3. To run the server, execute the following command in the backend directory:
   ```
   uvicorn main:app --reload
   ```