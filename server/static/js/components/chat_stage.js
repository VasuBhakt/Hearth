/**
 * Chat Stage Component: Renders user & assistant conversations, interactive plan briefing cards,
 * and handles user input submission.
 */
import { stateStore } from '../state.js';
import { renderPlanCardHtml, bindPlanCardEvents } from './plan_card.js';

export function initChatStage(elements, onSendMessage) {
  const { feedEl, inputEl, btnSendEl } = elements;
  if (!feedEl || !inputEl || !btnSendEl) return;

  // React to reactive state updates
  stateStore.subscribe((state) => {
    renderMessages(feedEl, state.messages, state.isThinking, (editPrompt) => {
      if (onSendMessage) {
        onSendMessage(editPrompt);
      }
    });

    btnSendEl.disabled = state.isThinking;
    inputEl.disabled = state.isThinking;
  });

  // Handle send action
  function submitInput() {
    const text = inputEl.value.trim();
    if (!text || stateStore.getState().isThinking) return;

    inputEl.value = '';
    if (onSendMessage) {
      onSendMessage(text);
    }
  }

  btnSendEl.addEventListener('click', submitInput);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitInput();
    }
  });
}

/**
 * Renders message rows into the chat feed container.
 */
function renderMessages(feedEl, messages, isThinking, onQuickEdit) {
  let html = '';

  for (const msg of messages) {
    const isUser = msg.role === 'user';
    const avatar = isUser ? '👤' : '🔥';
    const roleClass = isUser ? 'user' : 'assistant';

    let contentHtml = `<div class="message-bubble">${escapeHtml(msg.text)}</div>`;

    // Embed Plan Card widget if message has a plan attached
    if (msg.plan) {
      contentHtml = `
        <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
          ${msg.text ? `<div class="message-bubble">${escapeHtml(msg.text)}</div>` : ''}
          ${renderPlanCardHtml(msg.plan)}
        </div>
      `;
    }

    html += `
      <div class="chat-row ${roleClass}" id="${msg.id}">
        <div class="chat-avatar">${avatar}</div>
        <div style="display: flex; flex-direction: column; max-width: calc(100% - 50px);">
          ${contentHtml}
          <div class="message-time">${escapeHtml(msg.timestamp || '')}</div>
        </div>
      </div>
    `;
  }

  // If assistant is planning / calling MCP tools, show ambient skeleton
  if (isThinking) {
    html += `
      <div class="chat-row assistant thinking-row">
        <div class="chat-avatar">🔥</div>
        <div class="thinking-indicator">
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
        </div>
      </div>
    `;
  }

  feedEl.innerHTML = html;

  // Bind interactive buttons on Plan Cards (Approve, Undo, Quick Edit)
  bindPlanCardEvents(feedEl, onQuickEdit);

  // Auto scroll to latest update
  requestAnimationFrame(() => {
    feedEl.scrollTop = feedEl.scrollHeight;
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
