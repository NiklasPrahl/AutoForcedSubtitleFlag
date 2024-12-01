import os
import subprocess
import logging
from datetime import datetime
import json
import configparser

def load_config():
    """Load configuration from .config file"""
    config = configparser.ConfigParser()
    
    # Get the directory of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '.config')
    
    # Check if config file exists, if not create with defaults
    if not os.path.exists(config_path):
        config['Paths'] = {
            'mkv_folder': '/Volumes/Lager/mkv_test'
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)
    else:
        config.read(config_path)
    
    return config

def setup_logging(folder_path):
    log_file = os.path.join(folder_path, f'mkv_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

def should_be_forced(track, all_tracks):
    """
    Determine if a subtitle track should be forced based on:
    1. Less than 400 elements
    2. Less than 20% of the max elements for the same language
    """
    try:
        element_count = int(track['element_count'])
        language = track['language']
        
        # Get max elements for this language
        same_language_tracks = [t for t in all_tracks if t['language'] == language]
        max_elements = max(int(t['element_count']) for t in same_language_tracks)
        
        # Calculate percentage of max elements
        percentage = (element_count / max_elements) * 100 if max_elements > 0 else 100
        
        # Store percentage in track for logging
        track['percentage'] = percentage
        
        return element_count < 400 or percentage < 20
        
    except (ValueError, KeyError):
        return False

def analyze_subtitle_tracks(mediainfo_output):
    """Analyze subtitle tracks from mediainfo output"""
    subtitle_info = []
    
    for track in mediainfo_output['media']['track']:
        if track['@type'] == 'Text':
            subtitle_track = {
                'id': track.get('ID', 'unknown'),
                'format': track.get('Format', 'unknown'),
                'language': track.get('Language', 'unknown'),
                'forced': track.get('Forced', 'No'),
                'default': track.get('Default', 'No'),
                'element_count': track.get('Count_of_elements', '0')
            }
            
            if subtitle_track['element_count'] == '0':
                subtitle_track['element_count'] = track.get('Count of elements', '0')
            if subtitle_track['element_count'] == '0':
                subtitle_track['element_count'] = track.get('ElementCount', '0')
                
            subtitle_info.append(subtitle_track)
    
    # Add should_be_forced flag for each track
    for track in subtitle_info:
        track['should_be_forced'] = should_be_forced(track, subtitle_info)
    
    return subtitle_info

def parse_mkvinfo_output(mkvinfo_output):
    """Parse mkvinfo output to get track mapping"""
    track_mapping = {}
    current_track = None
    
    for line in mkvinfo_output.split('\n'):
        line = line.strip()
        
        if '| + Track' in line:
            current_track = {}
            logging.info(f"Found new track: {line}")
        elif current_track is not None:
            if 'Track number:' in line:
                try:
                    # Extract both track number and mkvmerge ID
                    # Example: "Track number: 45 (track ID for mkvmerge & mkvextract: 33)"
                    logging.info(f"Processing track number line: {line}")
                    parts = line.split('(')
                    track_num = parts[0].split(':')[1].strip()  # This corresponds to the MediaInfo ID
                    mkvmerge_id = parts[1].split(':')[1].split(')')[0].strip()  # This is the ID needed for mkvpropedit
                    current_track['number'] = track_num
                    current_track['mkvmerge_id'] = mkvmerge_id
                    logging.info(f"Extracted: MediaInfo/Track number {track_num}, MKVMerge ID {mkvmerge_id}")
                except Exception as e:
                    logging.error(f"Error parsing track numbers: {str(e)}")
            elif 'Track type:' in line and 'subtitles' in line.lower():
                if 'number' in current_track:
                    # Wir speichern die Track-Nummer als Key (entspricht MediaInfo ID)
                    track_mapping[current_track['number']] = current_track['mkvmerge_id']
                    logging.info(f"Added mapping: MediaInfo ID {current_track['number']} -> MKVMerge ID {current_track['mkvmerge_id']}")
                current_track = None
            elif 'Track type:' in line:
                current_track = None
    
    logging.info(f"Final track mapping: {track_mapping}")
    return track_mapping

def set_forced_flag(file_path, track_id, forced=True):
    """Set the forced flag for a specific track using mkvpropedit"""
    try:
        # Korrigiere die Track-ID um +1, da mkvpropedit die nächsthöhere ID verwendet
        corrected_track_id = int(track_id) + 1
        cmd = ['mkvpropedit', file_path, '--edit', f'track:{corrected_track_id}', 
               '--set', f'flag-forced={1 if forced else 0}']
        logging.debug(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.error(f"mkvpropedit error: {result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Failed to set forced flag: {str(e)}")
        return False

def analyze_and_fix_mkv_files(folder_path):
    if not os.path.exists(folder_path):
        raise ValueError(f"The specified folder path does not exist: {folder_path}")
    
    log_file = setup_logging(folder_path)
    logging.info(f"Starting MKV analysis for folder: {folder_path}")
    
    mkv_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.mkv')]
    
    if not mkv_files:
        logging.warning("No MKV files found in the specified folder")
        return
    
    logging.info(f"Found {len(mkv_files)} MKV files")
    
    for mkv_file in mkv_files:
        full_path = os.path.join(folder_path, mkv_file)
        logging.info(f"\nAnalyzing file: {mkv_file}")
        
        try:
            # Get MediaInfo data
            mediainfo_result = subprocess.run(['mediainfo', '--Full', '--Output=JSON', full_path], 
                                           capture_output=True, text=True)
            
            # Get MKVInfo data
            mkvinfo_result = subprocess.run(['mkvinfo', full_path], 
                                          capture_output=True, text=True)
            
            if mediainfo_result.returncode == 0 and mkvinfo_result.returncode == 0:
                mediainfo_data = json.loads(mediainfo_result.stdout)
                track_mapping = parse_mkvinfo_output(mkvinfo_result.stdout)
                
                # Debug output for track mapping
                logging.info("\nTrack ID Mapping Debug:")
                logging.info("MKVInfo track mapping:")
                logging.info(f"{track_mapping}")
                
                subtitle_tracks = analyze_subtitle_tracks(mediainfo_data)
                
                # Debug output for subtitle track IDs
                logging.info("\nMediaInfo subtitle track IDs:")
                subtitle_ids = [track['id'] for track in subtitle_tracks]
                logging.info(f"{subtitle_ids}")
                
                # Neue Debug-Ausgabe für alle ID-Tripel
                logging.info("\nID Triplets (MediaInfo ID, MKVInfo Track Number, MKVInfo Track ID for mkvmerge):")
                for track in subtitle_tracks:
                    mediainfo_id = track['id']
                    mkvinfo_track_num = mediainfo_id  # Diese sind identisch
                    mkvmerge_id = track_mapping.get(mediainfo_id, "not found")
                    logging.info(f"  Track: ({mediainfo_id}, {mkvinfo_track_num}, {mkvmerge_id})")
                
                if subtitle_tracks:
                    logging.info(f"\nFound {len(subtitle_tracks)} subtitle tracks:")
                    tracks_to_force = []
                    
                    # First, analyze all tracks
                    for track in subtitle_tracks:
                        element_info = (f"{track['element_count']} elements "
                                      f"({track.get('percentage', 0):.1f}% of max for {track['language']})")
                        
                        logging.info(f"\n  Track ID {track['id']}:")
                        logging.info(f"    Format: {track['format']}")
                        logging.info(f"    Language: {track['language']}")
                        logging.info(f"    Current forced flag: {track['forced']}")
                        logging.info(f"    Default: {track['default']}")
                        logging.info(f"    Elements: {element_info}")
                        logging.info(f"    Needs to be flagged as forced: {track['should_be_forced']}")
                        
                        if track['should_be_forced']:
                            tracks_to_force.append(track)
                    
                    # Then, summarize changes
                    if tracks_to_force:
                        logging.info(f"\nWill modify {len(tracks_to_force)} tracks in {mkv_file}:")
                        for track in tracks_to_force:
                            logging.info(f"  - Track {track['id']} ({track['language']}): "
                                       f"{track['element_count']} elements")
                        
                        # Apply changes
                        for track in tracks_to_force:
                            mkvmerge_id = track_mapping.get(track['id'])
                            if mkvmerge_id:
                                logging.info(f"\n  Setting forced flag for track {track['id']}:")
                                logging.info(f"    MKVMerge ID: {mkvmerge_id}")
                                logging.info(f"    Language: {track['language']}")
                                logging.info(f"    Elements: {track['element_count']}")
                                
                                success = set_forced_flag(full_path, mkvmerge_id)
                                track['modified'] = success  # Track the modification status
                                
                                if success:
                                    logging.info(f"    ✓ Successfully set forced flag")
                                else:
                                    logging.error(f"    ✗ Failed to set forced flag")
                            else:
                                logging.error(f"    ✗ Could not find mkvmerge ID for track {track['id']}")
                                track['modified'] = False
                    else:
                        logging.info("\nNo tracks need to be modified in this file")
                    
                    # Final verification
                    logging.info("\nFinal track status:")
                    for track in tracks_to_force:
                        logging.info(f"  Track {track['id']} ({track['language']}):")
                        logging.info(f"    Original forced flag: {track['forced']}")
                        logging.info(f"    Should be forced: Yes")
                        logging.info(f"    Number of elements: {track['element_count']}")
                        logging.info(f"    Action taken: {'Success' if track.get('modified', False) else 'Failed'}")
                
                else:
                    logging.info("No subtitle tracks found in this file")
                    
        except Exception as e:
            logging.error(f"Error processing {mkv_file}: {str(e)}")

if __name__ == "__main__":
    config = load_config()
    FOLDER_PATH = config['Paths']['mkv_folder']
    
    try:
        analyze_and_fix_mkv_files(FOLDER_PATH)
        logging.info("Analysis and fixes completed successfully")
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
