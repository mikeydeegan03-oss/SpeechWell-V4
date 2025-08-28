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
from collections import deque
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="SpeechWell Dysarthria Analysis Webhook")

# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Results storage for real-time display
recent_results = deque(maxlen=10)

def store_analysis_result(conversation_id: str, analysis_data: dict):
    """Store analysis result for API access."""
    result = {
        "conversation_id": conversation_id,
        "timestamp": datetime.now().isoformat(),
        "analysis": analysis_data
    }
    recent_results.append(result)
    print(f"💾 Stored result for: {conversation_id}")

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
    def estimate_speech_duration(text: str, estimated_wpm: float = 120) -> float:
        """Estimate speech duration based on word count and average speech rate."""
        word_count = len(text.split())
        # Convert WPM to words per second, then calculate duration
        estimated_duration = (word_count / estimated_wpm) * 60
        return round(estimated_duration, 2)
    
    @staticmethod
    def estimate_timing_from_conversation(transcript: List[Dict]) -> List[Dict]:
        """Estimate timing for user segments based on conversation flow."""
        user_segments = []
        cumulative_time = 0
        
        for turn in transcript:
            if turn.get('role') == 'user' and turn.get('message'):
                text = turn['message']
                # Estimate duration based on text length and complexity
                word_count = len(text.split())
                
                # More sophisticated duration estimation
                base_duration = word_count * 0.5  # 0.5 seconds per word (120 WPM)
                
                # Adjust for speech patterns that indicate slower speech
                pause_indicators = text.count('...') + text.count('..') + text.count(' ... ')
                hesitation_words = len([w for w in text.lower().split() if w in ['um', 'uh', 'er', 'ah']])
                
                # Add time for pauses and hesitations
                pause_time = pause_indicators * 1.0  # 1 second per pause indicator
                hesitation_time = hesitation_words * 0.5  # 0.5 seconds per hesitation
                
                estimated_duration = base_duration + pause_time + hesitation_time
                
                user_segments.append({
                    'text': text,
                    'timestamp': cumulative_time,
                    'duration': estimated_duration,
                    'estimated': True
                })
                
                cumulative_time += estimated_duration + 2.0  # Add 2 seconds for agent response
        
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
    def analyze_language_patterns(text: str) -> Dict:
        """Analyze language and communication patterns from text."""
        patterns = {
            'word_repetitions': 0,
            'self_corrections': 0,
            'incomplete_thoughts': 0,
            'filler_words': 0,
            'complex_words_attempted': 0,
            'sentence_fragments': 0
        }
        
        words = text.lower().split()
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        # Detect word repetitions (immediate repeats)
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and len(words[i]) > 2:
                patterns['word_repetitions'] += 1
        
        # Detect self-corrections (words that start similarly then change)
        correction_markers = ['i mean', 'no', 'actually', 'sorry', 'let me', 'or rather']
        for marker in correction_markers:
            patterns['self_corrections'] += text.lower().count(marker)
        
        # Detect incomplete thoughts (trailing off indicators)
        if text.endswith('...') or text.count('...') > 0:
            patterns['incomplete_thoughts'] += text.count('...')
        
        # Count filler words
        fillers = ['um', 'uh', 'er', 'ah', 'like', 'you know', 'well']
        for filler in fillers:
            patterns['filler_words'] += text.lower().count(filler)
        
        # Count complex/longer words (potential articulation challenges)
        patterns['complex_words_attempted'] = sum(1 for word in words if len(word) > 6)
        
        # Detect sentence fragments (very short sentences)
        patterns['sentence_fragments'] = sum(1 for s in sentences if len(s.split()) < 3)
        
        return patterns
    
    @staticmethod
    def analyze_communication_effectiveness(text: str) -> Dict:
        """Analyze communication effectiveness and completeness from text."""
        effectiveness = {
            'sentence_completion_rate': 0,
            'average_sentence_length': 0,
            'phrase_breaks': 0,
            'message_clarity_score': 100  # Start high, reduce for issues
        }
        
        # Analyze sentence structure
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        if sentences:
            sentence_lengths = [len(s.split()) for s in sentences]
            effectiveness['average_sentence_length'] = sum(sentence_lengths) / len(sentence_lengths)
            
            # Count incomplete sentences (very short or ending with ...)
            complete_sentences = sum(1 for s in sentences if len(s.split()) >= 3 and not s.endswith('...'))
            effectiveness['sentence_completion_rate'] = (complete_sentences / len(sentences)) * 100
        
        # Count phrase breaks (indicated by punctuation and pauses)
        effectiveness['phrase_breaks'] = text.count(',') + text.count('...') + text.count('..')
        
        # Reduce clarity score for communication barriers
        if effectiveness['sentence_completion_rate'] < 70:
            effectiveness['message_clarity_score'] -= 20
        if effectiveness['average_sentence_length'] < 3:
            effectiveness['message_clarity_score'] -= 15
        if effectiveness['phrase_breaks'] > len(text.split()) * 0.3:
            effectiveness['message_clarity_score'] -= 10
        
        effectiveness['message_clarity_score'] = max(0, effectiveness['message_clarity_score'])
        
        return effectiveness
    
    @staticmethod
    def analyze_verbal_fluency(text: str) -> Dict:
        """Analyze verbal fluency based on text patterns."""
        fluency_analysis = {
            'fluency_disruptions': 0,
            'hesitation_frequency': 0,
            'revision_attempts': 0,
            'flow_interruptions': 0,
            'overall_fluency_score': 100
        }
        
        text_lower = text.lower()
        word_count = len(text.split())
        
        # Count hesitation markers
        hesitations = ['um', 'uh', 'er', 'ah', 'hmm']
        hesitation_count = sum(text_lower.count(h) for h in hesitations)
        fluency_analysis['hesitation_frequency'] = hesitation_count
        
        # Count revision attempts
        revisions = ['i mean', 'no', 'actually', 'wait', 'sorry', 'let me try']
        revision_count = sum(text_lower.count(r) for r in revisions)
        fluency_analysis['revision_attempts'] = revision_count
        
        # Count flow interruptions (pauses, incomplete thoughts)
        interruptions = text.count('...') + text.count('..') + text.count(' - ')
        fluency_analysis['flow_interruptions'] = interruptions
        
        # Calculate total disruptions
        total_disruptions = hesitation_count + revision_count + interruptions
        fluency_analysis['fluency_disruptions'] = total_disruptions
        
        # Calculate fluency score (penalize disruptions relative to speech length)
        if word_count > 0:
            disruption_rate = total_disruptions / word_count
            penalty = min(80, disruption_rate * 200)  # Max 80 point penalty
            fluency_analysis['overall_fluency_score'] = max(20, 100 - penalty)
        
        return fluency_analysis
    
    @staticmethod
    def analyze_speech_segment(segment: Dict) -> Dict:
        """Analyze a single speech segment for dysarthria indicators."""
        text = segment['text']
        duration = segment.get('duration', 0)
        is_estimated = segment.get('estimated', False)
        
        # Basic metrics
        word_count = len(text.split())
        char_count = len(text.replace(' ', ''))
        speech_rate = SpeechAnalyzer.calculate_speech_rate(text, duration)
        pause_count = SpeechAnalyzer.count_pauses(text)
        
        # Text-based analysis (what we can actually measure)
        language_patterns = SpeechAnalyzer.analyze_language_patterns(text)
        communication_effectiveness = SpeechAnalyzer.analyze_communication_effectiveness(text)
        verbal_fluency = SpeechAnalyzer.analyze_verbal_fluency(text)
        
        # Core metrics
        analysis = {
            'text': text,
            'duration_seconds': duration,
            'timing_estimated': is_estimated,
            'word_count': word_count,
            'character_count': char_count,
            'speech_rate_wpm': speech_rate,
            'pause_count': pause_count,
            'speech_density': word_count / max(duration, 1),  # words per second
            'avg_word_length': char_count / max(word_count, 1),
        }
        
        # Communication challenges (what we can detect from text)
        analysis['communication_challenges'] = {
            'slow_speech_rate': speech_rate < 100 if speech_rate > 0 else False,
            'frequent_pauses': pause_count > word_count * 0.15,
            'short_responses': word_count < 5,
            'word_finding_difficulty': language_patterns['filler_words'] > 2,
            'incomplete_thoughts': language_patterns['incomplete_thoughts'] > 0,
            'frequent_self_corrections': language_patterns['self_corrections'] > 1,
            'communication_breakdown': communication_effectiveness['message_clarity_score'] < 60
        }
        
        # Add detailed text-based analysis
        analysis['language_patterns'] = language_patterns
        analysis['communication_effectiveness'] = communication_effectiveness
        analysis['verbal_fluency'] = verbal_fluency
        
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
    
    # Verify webhook signature (disabled for testing)
    # signature_header = request.headers.get("elevenlabs-signature")
    # if not verify_webhook_signature(body, signature_header):
    #     raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
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
    
    # Extract user speech segments with improved timing
    analyzer = SpeechAnalyzer()
    
    # Try to get segments with real timing first, fall back to estimation
    user_segments = analyzer.extract_user_speech_segments(transcript)
    
    # Check if we have real timing data
    has_real_timing = any(segment.get('duration', 0) > 0 for segment in user_segments)
    
    if not has_real_timing and user_segments:
        print("  ⚠️  No timing data from ElevenLabs - using estimation")
        # Use improved timing estimation
        user_segments = analyzer.estimate_timing_from_conversation(transcript)
    
    print(f"\nUser Speech Analysis:")
    print(f"  User speech segments found: {len(user_segments)}")
    print(f"  Timing method: {'Real timing data' if has_real_timing else 'Estimated timing'}")
    
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
        print(f"    Duration: {analysis['duration_seconds']:.1f}s {'(estimated)' if analysis.get('timing_estimated') else ''}")
        print(f"    Words: {analysis['word_count']}")
        print(f"    Speech rate: {analysis['speech_rate_wpm']:.1f} WPM")
        print(f"    Pauses detected: {analysis['pause_count']}")
        print(f"    Speech density: {analysis['speech_density']:.2f} words/sec")
        
        # Print comprehensive scoring
        language = analysis['language_patterns']
        effectiveness = analysis['communication_effectiveness']
        fluency = analysis['verbal_fluency']
        
        print(f"    📊 SCORES:")
        print(f"      Clarity: {effectiveness['message_clarity_score']:.0f}/100 | Fluency: {fluency['overall_fluency_score']:.0f}/100 | Completion: {effectiveness['sentence_completion_rate']:.0f}%")
        
        # Calculate additional scores
        repetition_score = max(0, 100 - (language['word_repetitions'] * 20))
        correction_score = max(0, 100 - (language['self_corrections'] * 15))
        filler_score = max(0, 100 - (language['filler_words'] * 10))
        
        print(f"      Repetitions: {repetition_score:.0f}/100 | Corrections: {correction_score:.0f}/100 | Fillers: {filler_score:.0f}/100")
        
        # Print communication challenges
        challenges = analysis['communication_challenges']
        active_challenges = [challenge for challenge, present in challenges.items() if present]
        if active_challenges:
            print(f"    ⚠️  Active Challenges: {', '.join(active_challenges)}")
        else:
            print(f"    ✅ No significant communication challenges detected")
        
        # Print specific pattern counts (condensed)
        if any([language['word_repetitions'], language['filler_words'], language['self_corrections'], language['incomplete_thoughts']]):
            print(f"    📋 Patterns: Reps:{language['word_repetitions']} | Fillers:{language['filler_words']} | Corrections:{language['self_corrections']} | Incomplete:{language['incomplete_thoughts']}")
        
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
        # Calculate overall session scores
        session_scores = {
            'message_clarity': 0,
            'verbal_fluency': 0,
            'sentence_completion': 0,
            'repetition_control': 0,
            'correction_frequency': 0,
            'filler_control': 0
        }
        
        segment_count = len(total_analysis['segments'])
        if segment_count > 0:
            for segment_analysis in total_analysis['segments']:
                lang = segment_analysis['language_patterns']
                eff = segment_analysis['communication_effectiveness']
                flu = segment_analysis['verbal_fluency']
                
                session_scores['message_clarity'] += eff['message_clarity_score']
                session_scores['verbal_fluency'] += flu['overall_fluency_score']
                session_scores['sentence_completion'] += eff['sentence_completion_rate']
                session_scores['repetition_control'] += max(0, 100 - (lang['word_repetitions'] * 20))
                session_scores['correction_frequency'] += max(0, 100 - (lang['self_corrections'] * 15))
                session_scores['filler_control'] += max(0, 100 - (lang['filler_words'] * 10))
            
            # Average the scores
            for key in session_scores:
                session_scores[key] = session_scores[key] / segment_count

        print(f"\n🎯 SESSION SUMMARY:")
        print(f"  📊 Overall Communication Scores:")
        print(f"    • Message Clarity: {session_scores['message_clarity']:.1f}/100")
        print(f"    • Verbal Fluency: {session_scores['verbal_fluency']:.1f}/100")
        print(f"    • Sentence Completion: {session_scores['sentence_completion']:.1f}%")
        print(f"    • Repetition Control: {session_scores['repetition_control']:.1f}/100")
        print(f"    • Self-Correction Management: {session_scores['correction_frequency']:.1f}/100")
        print(f"    • Filler Word Control: {session_scores['filler_control']:.1f}/100")
        
        # Calculate composite score
        composite_score = (
            session_scores['message_clarity'] * 0.25 +
            session_scores['verbal_fluency'] * 0.25 +
            session_scores['sentence_completion'] * 0.20 +
            session_scores['repetition_control'] * 0.10 +
            session_scores['correction_frequency'] * 0.10 +
            session_scores['filler_control'] * 0.10
        )
        
        print(f"\n  🏆 COMPOSITE COMMUNICATION SCORE: {composite_score:.1f}/100")
        
        # Provide clinical interpretation
        if composite_score >= 80:
            interpretation = "Excellent communication effectiveness"
            emoji = "🟢"
        elif composite_score >= 60:
            interpretation = "Good communication with minor challenges"
            emoji = "🟡"
        elif composite_score >= 40:
            interpretation = "Moderate communication challenges present"
            emoji = "🟠"
        else:
            interpretation = "Significant communication support needed"
            emoji = "🔴"
            
        print(f"  {emoji} Clinical Interpretation: {interpretation}")

        print(f"\n🏥 Clinical Assessment:")
        if overall_speech_rate < 100:
            print(f"  ⚠️  Speech rate below normal (100 WPM threshold)")
        else:
            print(f"  ✅ Speech rate within normal range")
            
        if pause_rate > 0.1:
            print(f"  ⚠️  High pause frequency detected")
        else:
            print(f"  ✅ Normal pause frequency")
            
        # Recommendations based on scores
        print(f"\n💡 Therapy Recommendations:")
        if session_scores['message_clarity'] < 70:
            print(f"  • Focus on sentence structure and clarity exercises")
        if session_scores['verbal_fluency'] < 70:
            print(f"  • Practice fluency-building exercises")
        if session_scores['sentence_completion'] < 70:
            print(f"  • Work on completing thoughts and sentences")
        if session_scores['filler_control'] < 80:
            print(f"  • Practice reducing filler words (um, uh)")
        if session_scores['repetition_control'] < 80:
            print(f"  • Focus on reducing word repetitions")
        if session_scores['correction_frequency'] < 80:
            print(f"  • Practice organizing thoughts before speaking")
            
        if composite_score >= 80:
            print(f"  • Continue current practice - excellent progress!")
        elif composite_score >= 60:
            print(f"  • Focus on identified challenge areas")
        else:
            print(f"  • Consider more intensive therapy support")

        # Store results for API access
        store_analysis_result(conversation_id, total_analysis)

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

@app.get("/api/latest-results")
async def get_latest_results():
    """Get all recent speech analysis results."""
    return {
        "status": "success",
        "results": list(recent_results),
        "count": len(recent_results)
    }

@app.get("/api/latest-result")
async def get_latest_result():
    """Get the most recent analysis result."""
    if recent_results:
        return {"status": "success", "result": recent_results[-1]}
    return {"status": "no_results", "message": "No results yet"}

if __name__ == "__main__":
    print("🎙️  SpeechWell Dysarthria Analysis Webhook Server")
    print("📡 Starting server on http://localhost:8000")
    print("🔗 Webhook endpoint: http://localhost:8000/webhook/elevenlabs")
    print("💡 Don't forget to set your WEBHOOK_SECRET!")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
