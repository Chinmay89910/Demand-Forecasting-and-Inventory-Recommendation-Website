// RestockIQ: Master Client Interactions & UI Controls

// Toast Notification Manager
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  const bgColors = {
    success: 'bg-[#1B4332] text-white',
    error: 'bg-red-700 text-white',
    warning: 'bg-amber-600 text-white',
    info: 'bg-[#2D6A4F] text-white',
  };

  toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg transform transition-all duration-300 ease-out translate-y-2 opacity-0 text-sm font-medium ${bgColors[type] || bgColors.info}`;
  toast.innerHTML = `
    <span class="flex-1">${message}</span>
    <button onclick="this.parentElement.remove()" class="opacity-75 hover:opacity-100 text-lg leading-none">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  }, 10);

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// AI Assistant Floating Drawer Toggle
function toggleAiDrawer() {
  const drawer = document.getElementById('ai-assistant-drawer');
  if (!drawer) return;
  if (drawer.classList.contains('drawer-closed')) {
    drawer.classList.remove('drawer-closed');
    drawer.classList.add('drawer-open');
    const input = document.getElementById('assistant-chat-input');
    if (input) input.focus();
  } else {
    drawer.classList.add('drawer-closed');
    drawer.classList.remove('drawer-open');
  }
}

// Grounded Assistant Chat State & History
window.assistantChatHistory = window.assistantChatHistory || [];

function resetAssistantChat() {
  window.assistantChatHistory = [];
  const chatMessages = document.getElementById('assistant-chat-messages');
  if (chatMessages) {
    chatMessages.innerHTML = `
      <div class="flex justify-start">
        <div class="bg-[#F3EFEA] border border-[#E5E0D8] text-[#1C1C19] px-4 py-3 rounded-2xl rounded-tl-none text-xs leading-relaxed max-w-[90%] shadow-xs">
          Conversation reset. I am your RestockIQ copilot. Ask me about today's forecast demand, active waste alerts, discount actions, or closing stock requirements.
        </div>
      </div>
    `;
  }
  showToast('Chat history cleared', 'info');
}

function formatAssistantMessage(text) {
  if (!text) return '';

  // 1. Normalize line breaks and split inline bullets onto newlines
  let clean = text.trim();
  // Split inline bullets before ** or after punctuation (. : ! ?)
  clean = clean.replace(/(\s+[\*•\-]\s+(?=\*\*)|(?<=[:.!?])\s*[\*•\-]\s+)/g, '\n* ');
  // Split inline bullets between items: e.g. "units. * **item**"
  clean = clean.replace(/(\.)\s*\*\s+/g, '.\n* ');

  // 2. Escape HTML tags to prevent XSS
  clean = clean.replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // 3. Bold text: **text**
  clean = clean.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-[#111827]">$1</strong>');

  // 4. Code / formula: `text`
  clean = clean.replace(/`([^`]+)`/g, '<code class="bg-[#EFEAE1] px-1.5 py-0.5 rounded text-[11px] font-mono text-[#1B4332]">$1</code>');

  // 5. Parse lines into structured elements
  const lines = clean.split('\n');
  let html = '';
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i].trim();
    if (!line) {
      if (inList) {
        html += '</div>';
        inList = false;
      }
      continue;
    }

    // Check if line is a bullet item
    const isBullet = line.startsWith('* ') || line.startsWith('- ') || line.startsWith('• ');
    let content = line.replace(/^[\*\-•]\s+/, '').trim();

    // Check if this line is a section header (e.g. bold title ending with colon or starting with #)
    const isHeader = (line.startsWith('#') || 
                      (content.startsWith('<strong') && (content.endsWith(':</strong>') || content.endsWith('</strong>:') || content.endsWith(':'))));

    if (isHeader) {
      if (inList) {
        html += '</div>';
        inList = false;
      }
      const headerText = content.replace(/^#+\s*/, '').replace(/<\/?strong[^>]*>/g, '').replace(/:\s*$/, '').trim();
      const isCritical = headerText.toLowerCase().includes('critical') || headerText.toLowerCase().includes('urgent');
      html += `
        <div class="mt-3 mb-1.5 font-bold text-xs text-[#1B4332] flex items-center gap-1.5 pb-1 border-b border-[#E5E0D8]">
          <span class="w-1.5 h-1.5 rounded-full ${isCritical ? 'bg-rose-500' : 'bg-amber-500'}"></span>
          <span>${headerText}</span>
        </div>
      `;
    } else if (isBullet) {
      if (!inList) {
        html += '<div class="space-y-1.5 my-1.5 pl-1">';
        inList = true;
      }
      html += `
        <div class="flex items-start gap-2 text-xs leading-relaxed text-[#1C1C19]">
          <span class="text-[#2D6A4F] font-bold text-sm leading-none mt-0.5 select-none">•</span>
          <div class="flex-1">${content}</div>
        </div>
      `;
    } else {
      if (inList) {
        html += '</div>';
        inList = false;
      }
      html += `<p class="text-xs leading-relaxed text-[#1C1C19] mb-1.5">${line}</p>`;
    }
  }

  if (inList) {
    html += '</div>';
  }

  return html;
}

// Send Assistant Chat Query
async function sendAssistantQuery(explicitQuery = null) {
  const input = document.getElementById('assistant-chat-input');
  const chatMessages = document.getElementById('assistant-chat-messages');
  if (!input || !chatMessages) return;

  const query = (explicitQuery || input.value).trim();
  if (!query) return;

  // Add User Message Bubble
  const userBubble = document.createElement('div');
  userBubble.className = 'flex justify-end';
  userBubble.innerHTML = `
    <div class="bg-[#1B4332] text-white px-4 py-2.5 rounded-2xl rounded-tr-none text-sm max-w-[85%] shadow-sm">
      ${query.replace(/</g, "&lt;").replace(/>/g, "&gt;")}
    </div>
  `;
  chatMessages.appendChild(userBubble);
  input.value = '';
  chatMessages.scrollTop = chatMessages.scrollHeight;

  // Typing Indicator
  const typingIndicator = document.createElement('div');
  typingIndicator.id = 'assistant-typing-indicator';
  typingIndicator.className = 'flex justify-start items-center gap-2 text-xs text-[#5A5A54] py-1';
  typingIndicator.innerHTML = `
    <span class="w-2 h-2 rounded-full bg-[#2D6A4F] animate-bounce"></span>
    <span class="w-2 h-2 rounded-full bg-[#2D6A4F] animate-bounce [animation-delay:0.2s]"></span>
    <span class="w-2 h-2 rounded-full bg-[#2D6A4F] animate-bounce [animation-delay:0.4s]"></span>
    <span>Consulting live store inventory...</span>
  `;
  chatMessages.appendChild(typingIndicator);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const res = await fetch('/api/v1/assistant/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: jsonEncodeSafely({
        query: query,
        history: window.assistantChatHistory || []
      }),
    });

    typingIndicator.remove();

    if (res.ok) {
      const data = await res.json();
      const answer = data.answer || "I could not retrieve an answer.";

      // Record to conversational history for natural follow-ups
      window.assistantChatHistory.push({ role: 'user', content: query });
      window.assistantChatHistory.push({ role: 'assistant', content: answer });
      if (window.assistantChatHistory.length > 10) {
        window.assistantChatHistory = window.assistantChatHistory.slice(-10);
      }

      const botBubble = document.createElement('div');
      botBubble.className = 'flex justify-start';
      botBubble.innerHTML = `
        <div class="bg-[#F3EFEA] border border-[#E5E0D8] text-[#1C1C19] px-4 py-2.5 rounded-2xl rounded-tl-none text-sm max-w-[90%] shadow-sm leading-relaxed">
          ${formatAssistantMessage(answer)}
        </div>
      `;
      chatMessages.appendChild(botBubble);
    } else {
      const errBubble = document.createElement('div');
      errBubble.className = 'flex justify-start';
      errBubble.innerHTML = `
        <div class="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-xl text-xs">
          Assistant query rate limited or unavailable. Try again shortly.
        </div>
      `;
      chatMessages.appendChild(errBubble);
    }
  } catch (e) {
    typingIndicator.remove();
    console.error('[Assistant Error]', e);
    showToast('Failed to reach AI Assistant', 'error');
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function jsonEncodeSafely(obj) {
  return JSON.stringify(obj);
}

// Quick Fill Demo Credentials
function fillDemoCredentials(email, password) {
  const emailInput = document.getElementById('email');
  const passwordInput = document.getElementById('password');
  if (emailInput && passwordInput) {
    emailInput.value = email;
    passwordInput.value = password;
    showToast(`Filled credentials for ${email}`, 'info');
  }
}

// Global System Health Polling (Every 60s)
async function refreshSystemHealth() {
  const pill = document.getElementById('system-health-pill');
  if (!pill) return;
  try {
    const res = await fetch('/health');
    if (res.ok) {
      const data = await res.json();
      const dbStatus = data.database?.status || 'connected';
      const llmStatus = data.llm?.status || 'active';
      pill.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-emerald-500 status-pulse"></span>
        <span class="text-xs font-semibold text-[#1B4332]">All Systems Online</span>
      `;
      pill.title = `DB: ${dbStatus} | LLM: ${llmStatus}`;
    }
  } catch (e) {
    pill.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-amber-500"></span>
      <span class="text-xs font-semibold text-amber-800">Local Mode</span>
    `;
    pill.title = 'Running on Resilient Local Persistence Engine';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  refreshSystemHealth();
});

