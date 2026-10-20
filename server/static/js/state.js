/**
 * Central Reactive State Store for Hearth Assistant Simulator.
 * Employs lightweight pub/sub pattern so components stay cleanly decoupled.
 */

class AppState {
  constructor() {
    this.state = {
      config: null,
      messages: [],
      activePlan: null,
      isThinking: false,
      isRecording: false,
      telemetryLogs: [],
    };
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  setConfig(config) {
    this.state.config = config;
    this.notify();
  }

  addMessage(role, text, plan = null) {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    this.state.messages.push({ role, text, plan, timestamp, id: `msg_${Date.now()}` });
    if (plan) {
      this.state.activePlan = plan;
    }
    this.notify();
  }

  setActivePlan(plan) {
    this.state.activePlan = plan;
    if (plan && plan.id) {
      for (const msg of this.state.messages) {
        if (msg.plan && msg.plan.id === plan.id) {
          msg.plan = { ...plan };
        }
      }
    }
    this.notify();
  }

  setThinking(isThinking) {
    this.state.isThinking = isThinking;
    this.notify();
  }

  setRecording(isRecording) {
    this.state.isRecording = isRecording;
    this.notify();
  }

  addTelemetryLog(entry) {
    this.state.telemetryLogs.unshift(entry); // newest first
    // Keep max 100 entries in frontend memory
    if (this.state.telemetryLogs.length > 100) {
      this.state.telemetryLogs.pop();
    }
    this.notify();
  }

  clearTelemetry() {
    this.state.telemetryLogs = [];
    this.notify();
  }
}

export const stateStore = new AppState();
