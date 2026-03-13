import math
import wave
import struct

def generate_tone(frequency, duration, sample_rate=44100, amplitude=0.5):
    """Generate a tone and save it as a WAV file"""
    # Calculate the number of samples
    num_samples = int(sample_rate * duration)
    
    # Create a wave file
    wav_file = wave.open('guten_tag.wav', 'w')
    wav_file.setparams((1, 2, sample_rate, num_samples, 'NONE', 'not compressed'))
    
    # Generate samples
    for i in range(num_samples):
        # Simple sine wave
        sample = amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)
        # Convert to 16-bit integer
        sample_int = int(sample * 32767)
        # Write the sample
        wav_file.writeframes(struct.pack('h', sample_int))
    
    wav_file.close()
    print("Audio file 'guten_tag.wav' has been generated.")

# Generate a simple tone as a placeholder for speech
# In a real application, you would use a TTS library
generate_tone(440, 2)  # 440Hz tone for 2 seconds