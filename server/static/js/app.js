/**
 * Main Application Bootstrap Orchestrator for Hearth Assistant Simulator.
 * Integrates modular components, manages real-time SSE stream, and drives state store.
 */
import { api } from './api.js';
import { stateStore } from './state.js';
import { initHeader } from './components/header.js';
import { initVoiceMic } from './components/voice_mic.js';
import { initChatStage } from './components/chat_stage.js';
import { initTelemetryHud } from './components/telemetry_hud.js';

document.addEventListener('DOMContentLoaded', async () => {
  // DOM Elements Map
  const headerElements = {
    titleEl: document.getElementById('header-title'),
    protocolPillEl: document.getElementById('protocol-badge'),
    btnSaturdayEl: document.getElementById('btn-scenario-saturday'),
    btnResetDbEl: document.getElementById('btn-reset-db'),
  };

  const chatElements = {
    feedEl: document.getElementById('chat-feed'),
    inputEl: document.getElementById('chat-input'),
    btnSendEl: document.getElementById('btn-send'),
  };

  const voiceMicElements = {
    btnMicEl: document.getElementById('btn-mic'),
    visualizerContainerEl: document.getElementById('audio-visualizer-container'),
    canvasEl: document.getElementById('audio-waveform-canvas'),
    inputEl: document.getElementById('chat-input'),
  };

  const telemetryElements = {
    feedEl: document.getElementById('telemetry-feed'),
    countPillEl: document.getElementById('telemetry-count-pill'),
    btnClearEl: document.getElementById('btn-clear-telemetry'),
  };

  /**
   * Unified dispatcher for user chat / voice / quick-edit messages
   */
  async function handleUserMessage(text) {
    if (!text || stateStore.getState().isThinking) return;

    // 1. Post user message to UI
    stateStore.addMessage('user', text);
    stateStore.setThinking(true);

    try {
      // 2. Dispatch to Hearth planner backend
      const activePlan = stateStore.getState().activePlan;
      const currentPlanId = activePlan ? activePlan.id : null;

      const res = await api.sendChatMessage(text, currentPlanId);

      // 3. Post assistant response and update active plan / schedule
      stateStore.addMessage('assistant', res.message, res.plan || null, res.schedule || null);
    } catch (err) {
      stateStore.addMessage('assistant', `⚠️ Error: ${err.message}`);
    } finally {
      stateStore.setThinking(false);
    }
  }

  // Initialize Modular Components
  initHeader(headerElements, handleUserMessage);
  initVoiceMic(voiceMicElements, handleUserMessage);
  initChatStage(chatElements, handleUserMessage);
  initTelemetryHud(telemetryElements);

  // Connect Real-Time SSE Telemetry Stream
  api.connectTelemetryStream(
    (logEntry) => {
      stateStore.addTelemetryLog(logEntry);
    },
    (err) => {
      console.warn('SSE Telemetry connection notice:', err);
    }
  );

  // Fetch Server & Model Configuration dynamically from backend (.env driven)
  try {
    const config = await api.fetchConfig();
    stateStore.setConfig(config);

    // Initial Welcome Message
    const defaultPrompt = config.default_prompt || "Get us ready for Saturday's tournament";
    stateStore.addMessage(
      'assistant',
      `Welcome to Hearth — your self-hosted, privacy-first family coordinator. You can type, speak with the mic, or click "${defaultPrompt}" above to launch the live tournament coordination scenario.`
    );
  } catch (err) {
    console.error('Failed to load initial configuration:', err);
    stateStore.addMessage('assistant', '⚠️ Notice: Could not connect to Hearth server. Please ensure the server is running.');
  }
});
