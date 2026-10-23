/**
 * Header Component: Manages brand identity, protocol status badge, and scenario quick actions.
 */
import { api } from '../api.js';
import { stateStore } from '../state.js';

export function initHeader(elements, onScenarioTrigger) {
  const { titleEl, protocolPillEl, btnSaturdayEl, btnResetDbEl } = elements;

  // React to configuration updates
  stateStore.subscribe((state) => {
    if (state.config && titleEl) {
      titleEl.textContent = state.config.title;
    }
    if (state.config && protocolPillEl) {
      protocolPillEl.innerHTML = `
        <span class="pulse-dot"></span>
        <span>MCP ${state.config.protocol_version} (Streamable HTTP)</span>
      `;
    }
  });

  // Scenario quick launch button
  if (btnSaturdayEl) {
    btnSaturdayEl.addEventListener('click', () => {
      const cfg = stateStore.getState().config;
      const prompt = cfg ? cfg.default_prompt : "Get us ready for the tournament";
      if (onScenarioTrigger) {
        onScenarioTrigger(prompt);
      }
    });
  }

  // Database reset button
  if (btnResetDbEl) {
    btnResetDbEl.addEventListener('click', async () => {
      try {
        btnResetDbEl.textContent = '🔄 Resetting...';
        btnResetDbEl.disabled = true;
        await api.resetDatabase();
        stateStore.setActivePlan(null);
        stateStore.addMessage('assistant', 'Database has been reset to the default Tournament scenario.');
      } catch (err) {
        alert('Reset failed: ' + err.message);
      } finally {
        btnResetDbEl.textContent = '🔄 Reset Scenario DB';
        btnResetDbEl.disabled = false;
      }
    });
  }
}
