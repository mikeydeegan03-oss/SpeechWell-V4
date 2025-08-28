"""
Test script for the SpeechWell webhook server.
Simulates ElevenLabs post-call webhook data.
"""

import requests
import json
from datetime import datetime

# Sample ElevenLabs transcript data for testing
sample_transcription_webhook = {
    "type": "post_call_transcription",
    "event_timestamp": int(datetime.now().timestamp()),
    "data": {
        "agent_id": "agent_8201k30y217yerkv9bzwekpsn5bt",
        "conversation_id": "test_conv_12345",
        "status": "done",
        "user_id": "test_user_001",
        "transcript": [
            {
                "role": "agent",
                "message": "Hello! I'm your speech therapy assistant. Let's practice some speech exercises today. Can you tell me about your morning routine?",
                "timestamp": 1000,
                "duration": 3.5
            },
            {
                "role": "user", 
                "message": "Good... morning. I... I woke up at... seven thirty. Then I... had... breakfast with... my family.",
                "timestamp": 4500,
                "duration": 8.2
            },
            {
                "role": "agent",
                "message": "That's wonderful! I noticed you're taking your time with your words, which is great for clarity. Can you tell me what you had for breakfast?",
                "timestamp": 12700,
                "duration": 4.1
            },
            {
                "role": "user",
                "message": "I had... scrambled eggs... and... toast. With... orange juice.",
                "timestamp": 16800,
                "duration": 6.3
            },
            {
                "role": "agent", 
                "message": "Excellent! Now let's try saying that same sentence a bit faster. Take a breath and tell me about your breakfast again.",
                "timestamp": 23100,
                "duration": 3.8
            },
            {
                "role": "user",
                "message": "I had scrambled eggs and toast... with orange juice.",
                "timestamp": 26900,
                "duration": 4.5
            }
        ],
        "metadata": {
            "start_time_unix_secs": int(datetime.now().timestamp()) - 300,
            "end_time_unix_secs": int(datetime.now().timestamp()),
            "user_id": "test_user_001"
        },
        "analysis": {
            "transcript_summary": "User practiced describing their morning routine and breakfast, showing improvement in speech fluency during the session.",
            "call_successful": True
        }
    }
}

def test_webhook():
    """Test the webhook endpoint with sample data."""
    webhook_url = "http://localhost:8000/webhook/elevenlabs"
    
    print("🧪 Testing SpeechWell Webhook Server")
    print(f"📡 Sending POST request to: {webhook_url}")
    
    try:
        # Send the test webhook
        response = requests.post(
            webhook_url,
            json=sample_transcription_webhook,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📋 Response Body: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Webhook test successful!")
        else:
            print("❌ Webhook test failed!")
            
    except requests.ConnectionError:
        print("❌ Could not connect to webhook server.")
        print("💡 Make sure the server is running: python webhook_server.py")
    except Exception as e:
        print(f"❌ Test error: {e}")

def test_health_check():
    """Test the health check endpoint."""
    health_url = "http://localhost:8000/health"
    
    try:
        response = requests.get(health_url)
        print(f"🏥 Health Check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")

if __name__ == "__main__":
    print("Testing webhook endpoints...")
    test_health_check()
    print("\n" + "="*50 + "\n")
    test_webhook()
