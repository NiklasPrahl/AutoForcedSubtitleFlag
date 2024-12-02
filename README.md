# AutoForcedSubtitleFlag

This Python script automatically analyzes MKV files and flags subtitle tracks as "forced" based on the number of elements in the track. It's particularly useful for movies and TV shows that are archived with MakeMKV and miss the correct forced flag.

NOTE: The matching of subtitle tracks is not tested against all existing subtitle formats, so unconventional formats might not be handled correctly yet.

## Usage 

Download the script and run it with the path to the folder containing your MKV files.

The path needs to be set in the .config file. See example_config.txt for reference.


## How it Works

The script identifies subtitle tracks that should be marked as "forced" based on two main criteria:
- Subtitle tracks with fewer than 400 elements
- Subtitle tracks with less than 20% of elements compared to other tracks of the same language

## Features

- Automatic detection of potential "forced" subtitle tracks
- Multi-language support
- Non-destructive MKV file editing
- Batch processing of multiple files

## Prerequisites

- Python 3.6 or higher
- MKVToolNix (mkvinfo, mkvpropedit)
- MediaInfo

IMPORTANT: This script is provided "as is" without any warranty. Use at your own risk. 

