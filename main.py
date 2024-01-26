import csv
import os
import subprocess
import re

import scrapetube

from config import channel_list


def setup_whisper_cpp_repo(model_version):
    repo_url = "https://github.com/ggerganov/whisper.cpp.git"
    repo_dir_name = "whisper.cpp"

    # Clone the repository
    subprocess.run(["git", "clone", repo_url])

    # Change directory to the cloned repository
    os.chdir(repo_dir_name)

    # Download the Whisper model in ggml format
    subprocess.run(["bash", "./models/download-ggml-model.sh", model_version])

    # Build the main example
    subprocess.run(["make"])

    # Change directory back to the original directory
    os.chdir("..")


def normalize_string(input_string):
    # Convert to lowercase
    normalized_str = input_string.lower()
    # Replace spaces with underscores
    normalized_str = normalized_str.replace(" ", "_")
    normalized_str = normalized_str.replace("|", "-")
    # Replace special characters with underscores
    normalized_str = re.sub(r'[^\w_-]', '_', normalized_str)
    # Remove consecutive underscores
    normalized_str = re.sub(r'_+', '_', normalized_str)
    # Remove leading or trailing underscores
    normalized_str = normalized_str.strip('_')
    return normalized_str


def extract_video_id(url):
    # Match the video ID in the URL
    match = re.search(r'(?:youtube\.com\/(?:watch\?v=|.*\/)|youtu\.be\/)([\w-]+)', url)
    if match:
        return match.group(1)
    else:
        raise ValueError('Invalid YouTube URL')


def generate_subtitles(video_id, language, title, project_path, model, keep_original=True):
    # Deleting original file output/ren/love_you_cnn.webm (pass -k to keep)
    mp3_path = os.path.join(project_path, f'{title}.mp3')
    if not os.path.isfile(mp3_path):
        # Download the YouTube video as an MP3 file
        if keep_original:
            command = f'yt-dlp -xvk --ffmpeg-location /opt/homebrew/bin/ffmpeg -o {mp3_path} --audio-format mp3 https://youtu.be/{video_id}'
        else:
            command = f'yt-dlp -xv --ffmpeg-location /opt/homebrew/bin/ffmpeg -o {mp3_path} --audio-format mp3 https://youtu.be/{video_id}'
        subprocess.run(f'zsh -c "{command}"', shell=True, check=True)

    wav_path = os.path.join(project_path, f'{title}.wav')
    if not os.path.isfile(wav_path):
        # Transcode the MP3 file into a 16KHz WAV file
        command = f'ffmpeg -i {mp3_path} -ar 16000 -ac 1 -c:a pcm_s16le {wav_path}'
        subprocess.run(f'zsh -c "{command}"', shell=True, check=True)

    if not os.path.isfile(f'{project_path}{title}.srt'):
        # Generate subtitles using the SpeechBrain model
        model_path = f'whisper.cpp/models/ggml-{model}.bin'
        output_path = os.path.join(project_path, title)
        command = f'./whisper.cpp/main -m {model_path} --output-srt -of {output_path} -f {wav_path} --language {language}'
        try:
            subprocess.run(f'zsh -c "{command}"', shell=True, check=True)
        except subprocess.CalledProcessError as e:
            setup_whisper_cpp_repo(model)
            subprocess.run(f'zsh -c "{command}"', shell=True, check=True)


def read_video_links(filename):
    video_id_title_dict = {}
    if not os.path.isfile(filename) or os.stat(filename).st_size == 0:
        return video_id_title_dict
    with open(filename) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        line_count = 0
        for row in csv_reader:
            video_id_title_dict[row[0]] = row[1]
            line_count += 1
    return video_id_title_dict


def get_video_links(channel_id, filename):
    videos = scrapetube.get_channel(channel_id)
    videos_collection = []
    for video in videos:
        videos_collection.append(f"{video['videoId']},\"{video['title']['runs'][0]['text']}\"")

    with open(filename, 'w') as f:
        for item in videos_collection:
            f.write(f"{item}\n")


def get_playlist_videos(playlist_id, filename):
    videos = scrapetube.get_playlist(playlist_id)
    videos_collection = []
    for video in videos:
        videos_collection.append(f"{video['videoId']},\"{video['title']['runs'][0]['text']}\"")

    with open(filename, 'w') as f:
        for item in videos_collection:
            f.write(f"{item}\n")


if __name__ == '__main__':
    output_directory = "output"
    all_videos_file = "_all_videos_.txt"
    # Get channel id from https://yt.lemnoslife.com/channels?handle=@osaznatotvorene

    # model_version = "tiny"
    # model_version = "base"
    # model_version = "small"
    # model_version = "medium"
    # model_version = "large"
    # model_version = "large-v2"
    # model_version = "large-v3"
    model_version = "large-v3-q5_0"

    for channel in channel_list:
        working_directory = os.path.join(output_directory, channel['channel_name'])
        os.makedirs(working_directory, exist_ok=True)
        file_path = os.path.join(working_directory, all_videos_file)
        if (channel.get("refresh_channel_videos") or not os.path.isfile(file_path)):
            # Add a check for playlist
            if channel.get("playlist_id"):
                get_playlist_videos(channel['playlist_id'], file_path)
            else:
                get_video_links(channel['channel_id'], file_path)

        working_directory = os.path.join(output_directory, channel['channel_name'])
        project_path = f"output/{channel['channel_name']}/"
        videos = read_video_links(os.path.join(working_directory, all_videos_file))
        for video_id in videos.keys():
            # Normalize the video title
            title = normalize_string(videos[video_id])

            # skip if srt file already exists
            if os.path.isfile(f'{project_path}{title}.srt'):
                continue

            # Generate the subtitles
            print(f"Generating subtitles for video ID: {video_id}, Title: {title}")
            generate_subtitles(video_id, channel["language"], title, working_directory, model_version, channel.get("keep_original"))

            # Delete the MP3 file
            if not channel.get("keep_mp3"):
                print(f"Deleting MP3 file: {title}.mp3")
                mp3_path = os.path.join(project_path, f'{title}.mp3')
                os.remove(mp3_path)

            # Delete the WAV file
            if not channel.get("keep_wav"):
                print(f"Deleting WAV file: {title}.wav")
                wav_path = os.path.join(project_path, f'{title}.wav')
                os.remove(wav_path)
