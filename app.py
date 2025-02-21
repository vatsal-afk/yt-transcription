import os
from dotenv import load_dotenv
import subprocess
import random
import tempfile
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import cloudinary
import cloudinary.uploader
import uvicorn
import logging
import shutil
import stat
import subprocess


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI()

# Get Cloudinary credentials from environment variables
required_env_vars = {
    "CLOUDINARY_CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "CLOUDINARY_API_KEY": os.getenv("CLOUDINARY_API_KEY"),
    "CLOUDINARY_API_SECRET": os.getenv("CLOUDINARY_API_SECRET")
}

# Check if all required environment variables are present
missing_vars = [key for key, value in required_env_vars.items() if not value]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Configure Cloudinary with environment variables
cloudinary.config( 
    cloud_name = required_env_vars["CLOUDINARY_CLOUD_NAME"],
    api_key = required_env_vars["CLOUDINARY_API_KEY"],
    api_secret = required_env_vars["CLOUDINARY_API_SECRET"]
)

class VideoURL(BaseModel):
    video_url: str

async def extract_audio(video_url: str, segment_time=30):
    temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    try:
        yt_command = ["yt-dlp", "-f", "bestaudio", "-o", "-", video_url]
        ffmpeg_command = [
            "ffmpeg", "-y", "-i", "pipe:0", 
            "-t", str(segment_time),
            "-acodec", "pcm_s16le", 
            "-ar", "16000", 
            "-ac", "1",
            temp_audio.name
        ]
        
        yt_process = subprocess.Popen(yt_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ffmpeg_process = subprocess.run(ffmpeg_command, stdin=yt_process.stdout, capture_output=True)
        
        if ffmpeg_process.returncode != 0:
            raise Exception(f"FFmpeg error: {ffmpeg_process.stderr.decode()}")
            
        if os.path.getsize(temp_audio.name) == 0:
            raise Exception("Generated audio file is empty")
            
        result = cloudinary.uploader.upload(
            temp_audio.name,
            resource_type="raw",
            folder="audio_segments"
        )
        return result['secure_url']
    finally:
        temp_audio.close()
        if os.path.exists(temp_audio.name):
            os.unlink(temp_audio.name)

async def transcribe_audio(audio_url: str):
    temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_dir = tempfile.mkdtemp()
    
    try:
        subprocess.run(["curl", "-o", temp_audio.name, audio_url], check=True)
        
        if os.path.getsize(temp_audio.name) == 0:
            raise Exception("Downloaded audio file is empty")
            
        whisper_command = [
            "whisper", 
            temp_audio.name, 
            "--model", "tiny",
            "--output_format", "txt", 
            "--output_dir", temp_dir
        ]
        subprocess.run(whisper_command, check=True)
        
        output_path = os.path.join(temp_dir, os.path.basename(temp_audio.name).replace('.wav', '.txt'))
        
        if not os.path.exists(output_path):
            raise Exception("Transcription file not generated")
            
        with open(output_path, "r") as f:
            transcription = f.read().strip()
            
        result = cloudinary.uploader.upload(
            output_path,
            resource_type="raw",
            folder="transcriptions"
        )
        return transcription, result['secure_url']
    finally:
        temp_audio.close()
        if os.path.exists(temp_audio.name):
            os.unlink(temp_audio.name)
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)

@app.post("/process_video")
async def process_video(video: VideoURL):
    try:
        audio_url = await extract_audio(video.video_url)
        transcription, transcription_url = await transcribe_audio(audio_url)
        fact_check_result = random.choice([True, False])
        
        return {
            "transcription": transcription,
            "transcription_url": transcription_url,
            "audio_url": audio_url,
            "fact_check_result": fact_check_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    subprocess.run(["ffmpeg", "-version"])
    uvicorn.run(app, host="0.0.0.0", port=8000)