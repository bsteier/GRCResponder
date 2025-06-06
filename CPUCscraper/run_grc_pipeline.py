import os
import subprocess
import sys
import time
import argparse

def main():
    """
    Run the GRC data pipeline:
    1. Extract proceeding IDs from proceedings.json
    2. Run threaded webscraper to collect data for these proceedings
    3. Run the threaded pipeline to insert data into database
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="GRC Data Pipeline")
    parser.add_argument("--threads", type=int, default=5, 
                        help="Number of worker threads for scraping proceedings (default: 5)")
    parser.add_argument("--doc-threads", type=int, default=3,
                        help="Number of worker threads per proceeding for document processing (default: 3)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit the number of proceedings to process (0 = no limit)")
    parser.add_argument("--scrape-only", action="store_true", 
                        help="Only run the webscraper, skip pipeline processing")
    parser.add_argument("--pipeline-only", action="store_true", 
                        help="Only run the pipeline, skip webscraping")
    args = parser.parse_args()
    
    # print("=== GRC DATA PIPELINE ===")
    # print("Starting pipeline at", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # # Step 1: Ensure proceeding_ids.txt exists
    # if not os.path.exists("proceeding_ids.txt"):
    #     print("Error: proceeding_ids.txt not found.")
    #     print("Please run extract_proceeding_ids.py first to generate this file.")
    #     return 1
    
    # # Count the number of proceeding IDs
    # with open("proceeding_ids.txt", "r") as f:
    #     proceeding_count = sum(1 for line in f if line.strip())
    
    # print(f"Found {proceeding_count} proceeding IDs to process")
    
    # # Skip webscraper if pipeline-only flag is set
    # if not args.pipeline_only:
    #     # Step 2: Run the threaded webscraper
    #     print("\n=== Running Threaded Webscraper ===")
    #     print("This will collect data for all proceedings in proceeding_ids.txt")
    #     print("Starting webscraper at", time.strftime("%Y-%m-%d %H:%M:%S"))
        
    #     try:
    #         # Ensure directories exist
    #         os.makedirs("metadata", exist_ok=True)
    #         os.makedirs("proceeding_links", exist_ok=True)
            
    #         # Build command with arguments
    #         webscraper_cmd = [
    #             "python", 
    #             "webscaper/threaded_webscraper.py", 
    #             "--threads", str(args.threads),
    #             "--doc-threads", str(args.doc_threads)
    #         ]
            
    #         # Add limit if specified
    #         if args.limit > 0:
    #             webscraper_cmd.extend(["--limit", str(args.limit)])
            
    #         # Run the webscraper
    #         webscraper_result = subprocess.run(
    #             webscraper_cmd, 
    #             check=True,
    #             capture_output=True,
    #             text=True
    #         )
            
    #         # Print the output
    #         print(webscraper_result.stdout)
    #         if webscraper_result.stderr:
    #             print("ERRORS:", webscraper_result.stderr)
                
    #     except subprocess.CalledProcessError as e:
    #         print(f"Error running webscraper: {e}")
    #         print(e.stderr)
    #         return 2
        
    #     print("Webscraper completed at", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # Skip pipeline if scrape-only flag is set
    if not args.scrape_only:
        # Step 3: Run the threaded pipeline to process the data
        print("\n=== Running Threaded Pipeline ===")
        print("This will insert collected data into the database")
        print("Starting pipeline at", time.strftime("%Y-%m-%d %H:%M:%S"))
        
        try:
            # Build command with arguments for the threaded pipeline
            pipeline_cmd = [
                "python", 
                "threaded_pipeline_fixed.py",
                "--proc-threads", str(args.threads),
                "--doc-threads", str(args.doc_threads)
            ]
            
            # Run the pipeline
            pipeline_result = subprocess.run(
                pipeline_cmd,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Print the output
            print(pipeline_result.stdout)
            if pipeline_result.stderr:
                print("ERRORS:", pipeline_result.stderr)
                
        except subprocess.CalledProcessError as e:
            print(f"Error running pipeline: {e}")
            print(e.stderr)
            return 3
        
        print("Pipeline completed at", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    print("\n=== Pipeline Complete ===")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 