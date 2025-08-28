# SpeechWell Webhook Server Setup

## Overview
This FastAPI webhook server receives ElevenLabs post-call data and analyzes speech for dysarthria indicators.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Server
```bash
python webhook_server.py
```

The server will start on `http://localhost:8000`

### 3. Test the Server
```bash
# In another terminal
python test_webhook.py
```

## Webhook Endpoints

- **POST** `/webhook/elevenlabs` - Main webhook endpoint for ElevenLabs
- **GET** `/` - Root endpoint (health check)
- **GET** `/health` - Health check endpoint

## Configuration

### Webhook Secret
In `webhook_server.py`, update the `WEBHOOK_SECRET` variable:
```python
WEBHOOK_SECRET = "your_actual_webhook_secret_from_elevenlabs"
```

### ElevenLabs Setup
1. Go to your ElevenLabs dashboard
2. Navigate to Conversational AI settings
3. Set up post-call webhook:
   - URL: `http://your-server.com/webhook/elevenlabs`
   - Enable "Send transcription data"
   - Copy the webhook secret

## Speech Analysis Features

### Dysarthria Indicators Detected:
- **Speech Rate**: Words per minute (normal: 120-160 WPM)
- **Pause Frequency**: Excessive pauses in speech
- **Speech Density**: Words per second
- **Utterance Length**: Very short responses

### Sample Output:
```
Call Information:
  Conversation ID: conv_12345
  Agent ID: agent_8201k30y217yerkv9bzwekpsn5bt
  Status: done
  Total transcript turns: 6

User Speech Analysis:
  User speech segments found: 3

  Segment 1:
    Text: 'Good... morning. I... I woke up at... seven thirty...'
    Duration: 8.2s
    Words: 12
    Speech rate: 87.8 WPM
    Pauses detected: 4
    Speech density: 1.46 words/sec
    ⚠️  Dysarthria indicators: slow_speech, many_pauses

📊 Overall Speech Analysis:
  Total speaking time: 19.0s
  Total words spoken: 25
  Overall speech rate: 78.9 WPM
  Total pauses: 6
  Pause rate: 24.00% (pauses per word)

🏥 Clinical Assessment:
  ⚠️  Speech rate below normal (100 WPM threshold)
  ⚠️  High pause frequency detected
```

## Development Notes

### Security
- HMAC signature verification is implemented but commented out for testing
- Uncomment signature verification lines in production
- Use IP whitelisting for additional security

### Extending Analysis
The `SpeechAnalyzer` class can be extended to include:
- Phoneme analysis
- Breath pattern detection
- Volume consistency
- Articulation scoring

## Production Deployment

### Using ngrok for Testing
```bash
# Install ngrok
# Start your webhook server
python webhook_server.py

# In another terminal
ngrok http 8000

# Use the ngrok URL in ElevenLabs webhook settings
```

### Production Considerations
- Use HTTPS in production
- Set up proper logging
- Enable webhook signature verification
- Add rate limiting
- Use a production WSGI server like Gunicorn
