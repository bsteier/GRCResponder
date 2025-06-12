# CPUC Document and Proceeding Downloader

The downloadPdfs.py Python script is designed to automate the download of PDF documents and their associated metadata from the California Public Utilities Commission (CPUC) website. It retrieves all proceeding information and downloads their relevant documents.

## Dependencies

To install the necessary dependencies, run the following command in terminal from the `grc_tools` directory:

``` pip install -r requirements.txt ```

Furthermore, since the proceeding scraper uses the `playwright` library, you will need to install the Chromium browser engine so simulate a chrome instance during the scraping process. Do this by running:

``` playwright install chromium ``` 

## Usage

To correctly store the downloaded files, you will need to configure the global variables defined at the top of the script. These variables include:

- `SAVE_DIR`: The directory where you will want to save the proceedings and their corresponding documents.
- `PROCEEDING_FILE`: The .json file where the proceeding metadata will be stored.

Once the global variables are set, you can run the script from the `grc_tools` directory using the following command:

``` python downloadPdfs.py ```

