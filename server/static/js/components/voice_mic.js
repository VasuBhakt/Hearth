/**
 * Voice Microphone Component: Native Web Speech API speech-to-text
 * with dynamic HTML5 Canvas waveform audio animation.
 */
import { stateStore } from '../state.js';

export function initVoiceMic(elements, onSpeechResult) {
  const { btnMicEl, visualizerContainerEl, canvasEl, inputEl } = elements;
  if (!btnMicEl || !canvasEl) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;
  let animationId = null;

  // Initialize Speech Recognition if browser supports it
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (inputEl) {
        inputEl.value = transcript;
      }
      if (onSpeechResult) {
        onSpeechResult(transcript);
      }
    };

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
    };
  }

  btnMicEl.addEventListener('click', () => {
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser. Please use the typed input bar.');
      return;
    }
    if (isListening) {
      recognition.stop();
      stopListening();
    } else {
      startListening();
    }
  });

  function startListening() {
    try {
      recognition.start();
      isListening = true;
      stateStore.setRecording(true);
      btnMicEl.classList.add('recording');
      btnMicEl.title = 'Listening... Click to stop';
      if (visualizerContainerEl) {
        visualizerContainerEl.classList.add('active');
      }
      startWaveAnimation();
    } catch (e) {
      console.error('Failed to start speech recognition:', e);
    }
  }

  function stopListening() {
    isListening = false;
    stateStore.setRecording(false);
    btnMicEl.classList.remove('recording');
    btnMicEl.title = 'Speak command';
    if (visualizerContainerEl) {
      visualizerContainerEl.classList.remove('active');
    }
    stopWaveAnimation();
  }

  // HTML5 Canvas Sine Waveform Animation
  const ctx = canvasEl.getContext('2d');
  let step = 0;

  function drawWave() {
    const width = (canvasEl.width = canvasEl.offsetWidth || 400);
    const height = (canvasEl.height = canvasEl.offsetHeight || 48);

    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#f97316';
    ctx.shadowBlur = 8;
    ctx.shadowColor = '#f97316';

    ctx.beginPath();
    for (let x = 0; x < width; x++) {
      const y = Math.sin((x * 0.03) + step) * Math.sin(step * 0.8) * 14 + height / 2;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    step += 0.08;
    animationId = requestAnimationFrame(drawWave);
  }

  function startWaveAnimation() {
    if (!animationId) {
      drawWave();
    }
  }

  function stopWaveAnimation() {
    if (animationId) {
      cancelAnimationFrame(animationId);
      animationId = null;
      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
    }
  }
}
