"""
FastAPI webhook server for receiving ElevenLabs post-call data 
and analyzing speech for dysarthria indicators.
"""

import json
import time
import hmac
import re
from hashlib import sha256
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="SpeechWell Dysarthria Analysis Webhook")

# Configuration - ElevenLabs webhook secret
WEBHOOK_SECRET = "wsec_fc1f6f93b5f48eaa24326b5ccacf01d85a9b23b861ed7d4ca85b033401178e05"

class SpeechAnalyzer:
    """Analyzes speech transcripts for dysarthria indicators."""
    
    @staticmethod
    def extract_user_speech_segments(transcript: List[Dict]) -> List[Dict]:
        """Extract only user speech segments from ElevenLabs transcript."""
        user_segments = []
        
        for turn in transcript:
            # ElevenLabs transcript format: role can be 'user' or 'agent'
            if turn.get('role') == 'user' and turn.get('message'):
                user_segments.append({
                    'text': turn['message'],
                    'timestamp': turn.get('timestamp', 0),
                    'duration': turn.get('duration', 0)
                })
        
        return user_segments
    
    @staticmethod
    def calculate_speech_rate(text: str, duration_seconds: float) -> float:
        """Calculate words per minute."""
        if duration_seconds <= 0:
            return 0.0
        
        # Count words (simple split by whitespace)
        word_count = len(text.split())
        
        # Convert to words per minute
        words_per_minute = (word_count / duration_seconds) * 60
        return round(words_per_minute, 2)
    
    @staticmethod
    def count_pauses(text: str) -> int:
        """Count potential pause indicators in speech."""
        # Count ellipses, multiple periods, and long gaps
        pause_patterns = [
            r'\.{2,}',  # Multiple periods
            r'…',       # Ellipsis
            r'  +',     # Multiple spaces
            r'\s*\.\s*\.\s*\.',  # Spaced periods
        ]
        
        pause_count = 0
        for pattern in pause_patterns:
            pause_count += len(re.findall(pattern, text))
        
        return pause_count
    
    @staticmethod
    def analyze_speech_segment(segment: Dict) -> Dict:
        """Analyze a single speech segment for dysarthria indicators."""
        text = segment['text']
        duration = segment.get('duration', 0)
        
        # Basic metrics
        word_count = len(text.split())
        char_count = len(text.replace(' ', ''))
        speech_rate = SpeechAnalyzer.calculate_speech_rate(text, duration)
        pause_count = SpeechAnalyzer.count_pauses(text)
        
        # Dysarthria indicators
        analysis = {
            'text': text,
            'duration_seconds': duration,
            'word_count': word_count,
            'character_count': char_count,
            'speech_rate_wpm': speech_rate,
            'pause_count': pause_count,
            'speech_density': word_count / max(duration, 1),  # words per second
            'avg_word_length': char_count / max(word_count, 1),
        }
        
        # Add dysarthria flags
        analysis['dysarthria_indicators'] = {
            'slow_speech': speech_rate < 100,  # Normal is 120-160 WPM
            'many_pauses': pause_count > word_count * 0.1,  # More than 10% pause rate
            'short_utterance': word_count < 5,
            'low_speech_density': analysis['speech_density'] < 1.5  # Less than 1.5 words/sec
        }
        
        return analysis

def verify_webhook_signature(request_body: bytes, signature_header: str) -> bool:
    """Verify the HMAC signature from ElevenLabs webhook."""
    if not signature_header:
        return False
    
    try:
        # Parse signature header: "t=timestamp,v0=hash"
        parts = signature_header.split(',')
        timestamp = parts[0].split('=')[1]
        signature = parts[1].split('=')[1]
        
        # Validate timestamp (within 30 minutes)
        current_time = int(time.time())
        if current_time - int(timestamp) > 30 * 60:
            print(f"Webhook timestamp too old: {timestamp}")
            return False
        
        # Calculate expected signature
        payload_to_sign = f"{timestamp}.{request_body.decode('utf-8')}"
        expected_signature = hmac.new(
            WEBHOOK_SECRET.encode('utf-8'),
            payload_to_sign.encode('utf-8'),
            sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(f"v0={expected_signature}", f"v0={signature}")
        
    except Exception as e:
        print(f"Error verifying webhook signature: {e}")
        return False

@app.post("/webhook/elevenlabs")
async def handle_elevenlabs_webhook(request: Request):
    """Handle incoming ElevenLabs post-call webhooks."""
    
    # Get request body
    body = await request.body()
    
    # Verify webhook signature
    signature_header = request.headers.get("elevenlabs-signature")
    if not verify_webhook_signature(body, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    try:
        # Parse JSON payload
        payload = json.loads(body.decode('utf-8'))
        
        print(f"\n{'='*50}")
        print(f"Received webhook at {datetime.now()}")
        print(f"Webhook type: {payload.get('type', 'unknown')}")
        print(f"{'='*50}")
        
        # Handle transcription webhooks
        if payload.get('type') == 'post_call_transcription':
            await process_transcription_webhook(payload)
        elif payload.get('type') == 'post_call_audio':
            await process_audio_webhook(payload)
        else:
            print(f"Unknown webhook type: {payload.get('type')}")
        
        return JSONResponse(content={"status": "received"}, status_code=200)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_transcription_webhook(payload: Dict):
    """Process transcription webhook with speech analysis."""
    data = payload.get('data', {})
    
    # Extract basic call information
    conversation_id = data.get('conversation_id', 'unknown')
    agent_id = data.get('agent_id', 'unknown')
    status = data.get('status', 'unknown')
    transcript = data.get('transcript', [])
    
    print(f"\nCall Information:")
    print(f"  Conversation ID: {conversation_id}")
    print(f"  Agent ID: {agent_id}")
    print(f"  Status: {status}")
    print(f"  Total transcript turns: {len(transcript)}")
    
    # Extract user speech segments
    analyzer = SpeechAnalyzer()
    user_segments = analyzer.extract_user_speech_segments(transcript)
    
    print(f"\nUser Speech Analysis:")
    print(f"  User speech segments found: {len(user_segments)}")
    
    if not user_segments:
        print("  No user speech found in transcript")
        return
    
    # Analyze each user speech segment
    total_analysis = {
        'total_words': 0,
        'total_duration': 0,
        'total_pauses': 0,
        'segments': []
    }
    
    for i, segment in enumerate(user_segments, 1):
        print(f"\n  Segment {i}:")
        analysis = analyzer.analyze_speech_segment(segment)
        
        # Print segment analysis
        print(f"    Text: '{analysis['text'][:100]}{'...' if len(analysis['text']) > 100 else ''}'")
        print(f"    Duration: {analysis['duration_seconds']:.1f}s")
        print(f"    Words: {analysis['word_count']}")
        print(f"    Speech rate: {analysis['speech_rate_wpm']:.1f} WPM")
        print(f"    Pauses detected: {analysis['pause_count']}")
        print(f"    Speech density: {analysis['speech_density']:.2f} words/sec")
        
        # Print dysarthria indicators
        indicators = analysis['dysarthria_indicators']
        flags = [flag for flag, present in indicators.items() if present]
        if flags:
            print(f"    ⚠️  Dysarthria indicators: {', '.join(flags)}")
        else:
            print(f"    ✅ No significant dysarthria indicators")
        
        # Add to totals
        total_analysis['total_words'] += analysis['word_count']
        total_analysis['total_duration'] += analysis['duration_seconds']
        total_analysis['total_pauses'] += analysis['pause_count']
        total_analysis['segments'].append(analysis)
    
    # Calculate overall metrics
    if total_analysis['total_duration'] > 0:
        overall_speech_rate = (total_analysis['total_words'] / total_analysis['total_duration']) * 60
        pause_rate = total_analysis['total_pauses'] / max(total_analysis['total_words'], 1)
        
        print(f"\n📊 Overall Speech Analysis:")
        print(f"  Total speaking time: {total_analysis['total_duration']:.1f}s")
        print(f"  Total words spoken: {total_analysis['total_words']}")
        print(f"  Overall speech rate: {overall_speech_rate:.1f} WPM")
        print(f"  Total pauses: {total_analysis['total_pauses']}")
        print(f"  Pause rate: {pause_rate:.2%} (pauses per word)")
        
        # Overall assessment
        print(f"\n🏥 Clinical Assessment:")
        if overall_speech_rate < 100:
            print(f"  ⚠️  Speech rate below normal (100 WPM threshold)")
        else:
            print(f"  ✅ Speech rate within normal range")
            
        if pause_rate > 0.1:
            print(f"  ⚠️  High pause frequency detected")
        else:
            print(f"  ✅ Normal pause frequency")

async def process_audio_webhook(payload: Dict):
    """Process audio webhook (basic logging for now)."""
    data = payload.get('data', {})
    
    conversation_id = data.get('conversation_id', 'unknown')
    agent_id = data.get('agent_id', 'unknown')
    has_audio = 'full_audio' in data
    
    print(f"\nAudio Webhook Received:")
    print(f"  Conversation ID: {conversation_id}")
    print(f"  Agent ID: {agent_id}")
    print(f"  Audio data present: {has_audio}")
    
    if has_audio:
        audio_data = data['full_audio']
        print(f"  Audio data size: {len(audio_data)} characters (base64)")
        print("  📎 Audio analysis not implemented yet")

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "SpeechWell Dysarthria Analysis Webhook Server", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check for monitoring."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    print("🎙️  SpeechWell Dysarthria Analysis Webhook Server")
    print("📡 Starting server on http://localhost:8000")
    print("🔗 Webhook endpoint: http://localhost:8000/webhook/elevenlabs")
    print("💡 Don't forget to set your WEBHOOK_SECRET!")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
