import os
import vlc
import time
import argparse

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
#Assemble your video list
def get_video_files(folder_path):
    video_extensions = ['.mp4', '.avi', '.mkv', '.flv', '.mov']
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.splitext(f)[1] in video_extensions]
    return sorted(files)

#Handles playing the current video (banner or episode)
def play_video(video_path, test_mode=False):
    logger.info(f"Attempting to play video: {video_path}")
    
    # Initialize VLC instance
    if test_mode:
        vlc_instance = vlc.Instance("--no-xlib --quiet")
        logger.info("VLC Test instance initialized.")
    else:
        vlc_instance = vlc.Instance("--no-xlib --quiet --fullscreen --video-on-top")
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
    if test_mode:
        player.set_fullscreen(False)
    else:
        player.set_fullscreen(True)
    
    if test_mode:
        logger.info("Test mode active. Playing video for 5 seconds only.")
        time.sleep(5)
        player.stop()
    else:
        # Wait for video to start playing
        while not player.is_playing():
            logger.debug("Waiting for video to start playing...")
            time.sleep(1)

        logger.info("Video started playing.")
    
        # Wait for video to finish playing
        while player.is_playing():
            logger.debug("Video is playing...")
            time.sleep(1)
        
        logger.info("Video playback completed.")
        player.stop()

# Extract the episode title from the filename
def extract_episode_title(episode_name):
    """Extracts the episode title or returns an empty string if the input is empty."""
    # If the input string is empty, return an empty string
    if not episode_name:
        return ""
    
    segments = episode_name.split(' - ')
    
    # If there are at least three segments, extract the episode title
    if len(segments) >= 3:
        return segments[2].rsplit('.', 1)[0]
    
    # Otherwise, return the entire input string
    return episode_name

def set_obs_text_title(banner_text, banner_file_path):    

    try:
        # Update the bannertext.txt file with the extracted episode title
        with open(banner_file_path, 'w') as file:
            file.write(banner_text)
        logger.info(f"Updated bannertext.txt with: {banner_text}")
    except Exception as e:
        logger.error(f"Error updating bannertext.txt: {e}")

#Main function
def main(test_mode=False):

    # SET ENV VARIABLES HERE
    
    #folder_path = input("Enter the path to the video folder: ")
    folder_path = r"D:\TV\Over the Garden Wall (2014)\Season 1"
    #banner_video = input("Enter the path to the banner video: ")
    banner_video = r"C:\Users\Eidolon\Videos\banner\banner.mp4"
    # banner_file_path = input("Enter the path to the banner text file: ")
    banner_file_path = r"C:\Users\Eidolon\Videos\banner\bannertext.txt"
    
    logger.info('Loading video queue from folder...')
    video_queue = get_video_files(folder_path)

    try:
        while True:
            if not video_queue:
                logger.info('Reloading video queue from folder...')
                video_queue = get_video_files(folder_path)

            # Set the title text of the next episode on OBS
            next_episode_title = os.path.basename(video_queue[0])
            banner_text = extract_episode_title(next_episode_title)
            logger.info(f'Setting OBS title text to: {banner_text}')
            set_obs_text_title(banner_text, banner_file_path)

            # Play banner video
            logger.info('Playing banner video...')
            play_video(banner_video, test_mode=test_mode)

            # Remove the title text overlay from OBS
            logger.info('Clearing OBS title text...')
            set_obs_text_title("", banner_file_path)

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
