import pyttsx3

# Initialize the TTS engine
engine = pyttsx3.init()

# Set properties (optional)
engine.setProperty('rate', 150)  # Speed of speech
engine.setProperty('volume', 0.9)  # Volume level (0.0 to 1.0)

# Text to speak
text = "guten tag"

# Save to file
engine.save_to_file(text, 'guten_tag.mp3')

# Run the engine
engine.runAndWait()

print("Audio file 'guten_tag.mp3' has been generated.")