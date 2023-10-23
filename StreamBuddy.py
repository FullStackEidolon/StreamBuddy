import os
import vlc
import time
import argparse
import xml.etree.ElementTree as ET
import logging
import tkinter as tk
from tkinter import filedialog
import urllib.parse

#Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Function to select a folder
def select_folder(dialog_title="Select a folder"):
    root = tk.Tk()  # Create a root window
    root.withdraw()  # Hide the root window

    folder_selected = filedialog.askdirectory(title=dialog_title)  # Open folder selection dialog
    return folder_selected
# Select a file function
def select_file(dialog_title="Select a file", filetypes=None):
    """
    Open a file selection dialog.

    Args:
        dialog_title (str): Title for the file selection dialog.
        filetypes (list): List of tuples specifying the file types to filter. Each tuple contains a description and a file extension pattern.

    Returns:
        str: Path of the selected file.
    """
    root = tk.Tk()  # Create a root window
    root.withdraw()  # Hide the root window

    if filetypes is None:
        filetypes = [("All files", "*.*")]

    file_selected = filedialog.askopenfilename(title=dialog_title, filetypes=filetypes)
    return file_selected



#Assemble your video list
# Video list from folder
def get_video_files(folder_path):
    video_extensions = ['.mp4', '.avi', '.mkv', '.flv', '.mov']
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.splitext(f)[1] in video_extensions]
    return sorted(files)

#Video list from .xspf
def queueBuilder(file_path):
    # Parse the XML file
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Namespace for XSPF
    ns = {'xspf': 'http://xspf.org/ns/0/'}
    
    # List to hold the queue
    queue = []

    # Iterate through each track in the playlist
    for track in root.findall('xspf:trackList/xspf:track/xspf:location', ns):
        location = track.text
        # Remove the "file://" prefix from the location
        location_cleaned = location.replace("file:///", "")
        # Decode the URL-encoded path
        location_decoded = urllib.parse.unquote(location_cleaned)
        queue.append(location_decoded)

    return queue

#Handles playing the current video (banner or episode)
def play_video(video_path, test_mode=False, banner_folder_path=None):
    logger.info(f"Attempting to play video: {video_path}")
    
    # Initialize VLC instance
    if test_mode:
        vlc_instance = vlc.Instance("--no-xlib --quiet")
        logger.info("VLC Test instance initialized.")
    else:
        vlc_instance = vlc.Instance("--no-xlib --quiet --fullscreen")
        logger.info("VLC instance initialized.")
    
    # Create a new media player object
    player = vlc_instance.media_player_new()
    logger.info("Media player object created.")
    
    # Set media resource locator
    player.set_mrl(video_path)
    logger.info(f"Media resource locator set to: {video_path}")
    
    # Play the video
    player.play()
    logger.info("Play command sent to VLC player.")
    
    # Wait for the video to start playing
    while not player.is_playing():
        logger.debug("Waiting for video to start playing...")
        time.sleep(1)
    
    # Try to get the duration until a valid duration is fetched
    duration_milliseconds = 0
    while duration_milliseconds <= 0:
        duration_milliseconds = player.get_length()
        time.sleep(0.5)  # Slight delay before rechecking
    
    duration_seconds = duration_milliseconds / 1000
    logger.info(f"Video duration: {duration_seconds} seconds")
    
    if test_mode:
        player.set_fullscreen(False)
        logger.info("Test mode active. Playing video for 5 seconds only.")
        time.sleep(20)
        player.stop()
    else:
        player.set_fullscreen(True)
        
        # Sleep until 2 seconds before the video ends (ensure non-negative value)
        sleep_time = max(0, duration_seconds - 2)
        time.sleep(sleep_time)
        
        # Remove the title text overlay from OBS
        logger.info('Clearing OBS title text...')
        set_obs_text_title("", "", "", banner_folder_path)
        
        # Sleep for the remaining time or at least 2 seconds
        time.sleep(min(2, duration_seconds - sleep_time))
        
        # Wait for video to finish playing
        while player.is_playing():
            logger.debug("Video is playing...")
            time.sleep(1)
        
        logger.info("Video playback completed.")
        player.stop()



# Extract the episode title from the filename
def extract_episode_title(episode_name):
    """Extracts the episode title based on the naming conventions."""
    # If the input string is empty, return an empty string
    if not episode_name:
        return ""
    
    # Remove the file extension
    episode_name = episode_name.rsplit('.', 1)[0]
    
    # Split the string based on ' - ' delimiter
    segments = episode_name.split(' - ')
    
    # Check for the naming convention "Show Name - Episode#Season# - Episode Title"
    if len(segments) == 3:
        return f"{segments[0]} - {segments[2]}"
    
    # Check for the naming convention "Show Name - Episode Title"
    elif len(segments) == 2:
        return f"{segments[0]} - {segments[1]}"
    
    # If none of the conventions match, return the entire input string
    return episode_name

def set_obs_text_title(last_episode_title, current_episode_title, next_episode_title, banner_folder_path):    
    # Default messages for last and next episodes
    if last_episode_title is None:
        last_episode_title = "Welcome to the stream!"
    if next_episode_title is None:
        next_episode_title = "Thanks for watching!"
    
    logger.info(f"Setting OBS title text to: Last: {last_episode_title}, Current: {current_episode_title},  Next: {next_episode_title}")
    
    # Define the file paths for the three text files
    last_episode_file = os.path.join(banner_folder_path, "last_episode.txt")
    current_episode_file = os.path.join(banner_folder_path, "current_episode.txt")
    next_episode_file = os.path.join(banner_folder_path, "next_episode.txt")

    # Helper function to write to a file and log the action
    def write_and_log(file_path, content):
        try:
            with open(file_path, 'w') as file:
                file.write(content)
            logger.info(f"Updated {file_path} with: {content}")
        except Exception as e:
            logger.error(f"Error updating {file_path}: {e}")

    # Update the three text files
    write_and_log(last_episode_file, last_episode_title)
    write_and_log(current_episode_file, current_episode_title)
    write_and_log(next_episode_file, next_episode_title)

#Main function
def main(test_mode=False):

    # SET ENV VARIABLES HERE 
    queue_xspf_location = select_file(dialog_title="Select an XSPF playlist", filetypes=[("XSPF files", "*.xspf"), ("All files", "*.*")])
    logger.info('Set up a folder with three text files for the banner text. The text files should be named lastEpisode.txt, currentEpisode.txt, and nextEpisode.txt.')
    banner_folder_path = select_folder("Select a folder with banner text files")
    bumper_video_folder_path = select_folder("Select a folder with bumper videos")
    #banner_video = select_file(dialog_title="Select a banner video", filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")])
    
    #Set up indexes for looping
    current_episode_index = -1
    bumper_index = 0
    logger.info('Loading video and bumper queue...')
    
    #video_queue = queueBuilder(folder_path)
    #Q: how do I use queueBuilder instead of queueBuilder?
    video_queue = queueBuilder(queue_xspf_location)
    bumper_queue = get_video_files(bumper_video_folder_path)
    try:
        while True:
            if not video_queue or current_episode_index == len(video_queue) - 1:
                logger.info('Reloading video queue from folder...')
                video_queue = queueBuilder(queue_xspf_location)
                current_episode_index = 0

            # Get the last, current, and next episode titles
            last_episode = video_queue[current_episode_index - 1] if current_episode_index > 0 else None
            current_episode = video_queue[current_episode_index]
            next_episode = video_queue[current_episode_index + 1] if current_episode_index < len(video_queue) - 1 else None

            # Extract titles
            last_episode_title = extract_episode_title(os.path.basename(last_episode)) if last_episode else None
            current_episode_title = extract_episode_title(os.path.basename(current_episode))
            next_episode_title = extract_episode_title(os.path.basename(next_episode)) if next_episode else None

            # Set the title text of the next episode on OBS
            #logger.info(f'Setting OBS title text to: Last: {last_episode_title}, Current: {current_episode_title},  Next: {next_episode_title}')
            set_obs_text_title(last_episode_title, current_episode_title, next_episode_title, banner_folder_path)
        
            # Increment the index for next iteration (simulate playing the current episode)
            current_episode_index += 1

            # Play bumper video
            current_bumper_video = bumper_queue[bumper_index]
            logger.info(f'Playing bumper video: {current_bumper_video}')
            play_video(current_bumper_video, test_mode=test_mode, banner_folder_path=banner_folder_path)


            # Remove the title text overlay from OBS
            logger.info('Clearing OBS title text...')
            set_obs_text_title("", "", "", banner_folder_path)

            # Increment bumper index or reset if we've reached the end of bumper_queue
            bumper_index = (bumper_index + 1) % len(bumper_queue)

            # Play the next episode
            next_episode = video_queue.pop(0)
            logger.info(f'Playing episode: {next_episode}')
            play_video(next_episode, test_mode=test_mode)
    
    except KeyboardInterrupt:
        # If you interrupt the script (e.g., Ctrl+C), it will disconnect gracefully
        logger.info('Killing StreamBuddy...')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='StreamBuddy script to manage video playback in VLC with OBS integration.')
    parser.add_argument('--test', action='store_true', help='Enable test mode to play each video for 5 seconds only.')
    args = parser.parse_args()

    main(test_mode=args.test)
