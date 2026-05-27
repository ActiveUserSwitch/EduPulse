from faster_whisper import WhisperModel

# Load the tiny model (fastest)
model = WhisperModel("tiny", device="cpu", compute_type="int8")

# Test transcription (we'll use a sample later)
print("Model loaded successfully!")
