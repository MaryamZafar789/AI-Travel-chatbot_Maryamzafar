
/*
 * LOCAL TRAVEL AI CHATBOT
 * Redesigned UI — API functionality preserved
 */

(function () {

  const scriptTag = document.currentScript;

  const API_BASE =
    scriptTag.getAttribute("data-api-base") ||
    "http://127.0.0.1:8001";

  let sessionId = null;
  let sessionReady = false;
  let busy = false;


  /* =========================================================
     ICONS
     ========================================================= */

  const PLANE_ICON = `
    <svg viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round">
      <path d="M3 12L21 4L13 22L11 13L3 12Z"/>
    </svg>
  `;


  /* =========================================================
     CHATBOT MARKUP
     ========================================================= */

  const root = document.createElement("div");

  root.className = "ltc-widget";

  root.innerHTML = `

    <!-- Floating Chat Button -->

    <button
      class="ltc-fab"
      aria-label="Open Travel Assistant"
    >
      ${PLANE_ICON}
    </button>


    <!-- CHAT PANEL -->

    <div class="ltc-panel" hidden>


      <!-- HEADER -->

      <div class="ltc-header">

        <div class="ltc-brand">

          <div class="ltc-brand-icon">
            ✈
          </div>

          <div>

            <div class="ltc-header-title">
              Travel Assistant
            </div>

            <div class="ltc-header-sub">
              Your personal travel guide
            </div>

          </div>

        </div>


        <button
          class="ltc-close"
          aria-label="Close chat"
        >
          ×
        </button>

      </div>


      <!-- PERFORATION -->

      <div class="ltc-perforation">

        <div class="ltc-perforation-notch left"></div>

        <div class="ltc-perforation-notch right"></div>

      </div>


      <!-- =================================================
           ACTUAL AI CHAT AREA
           ================================================= -->

      <div
        class="ltc-messages"
        id="ltc-messages"
      >

        <!-- Welcome screen -->

        <div class="ltc-welcome">

          <div class="ltc-welcome-image"></div>

          <div class="ltc-welcome-content">

            <div class="ltc-welcome-title">
              Welcome, traveller 👋
            </div>

            <div class="ltc-welcome-text">
              I'm your Travel AI Assistant.
              Ask me anything about visas,
              tickets, tours, Umrah packages,
              or travel insurance.
            </div>

          </div>

        </div>


        <!-- AI assistant message -->

        <div class="ltc-bubble ltc-bot">

          Assalam-o-Alaikum! 👋
          How can I help you plan your journey today?

        </div>

      </div>


      <!-- QUICK ACTIONS -->

      <div class="ltc-quick-title">
        What can I help you with?
      </div>


      <div class="ltc-suggested">

        <button
          data-q="What documents are required for a UAE visit visa?"
        >
          <span>🛂</span>
          <div>
            <strong>Visa</strong>
            <small>Requirements</small>
          </div>
        </button>


        <button
          data-q="Tell me about Umrah packages"
        >
          <span>🕋</span>
          <div>
            <strong>Umrah</strong>
            <small>Packages</small>
          </div>
        </button>


        <button
          data-q="What travel insurance do I need?"
        >
          <span>🛡️</span>
          <div>
            <strong>Insurance</strong>
            <small>Travel cover</small>
          </div>
        </button>


        <button
          data-q="Tell me about international tour packages"
        >
          <span>🌍</span>
          <div>
            <strong>Tours</strong>
            <small>Destinations</small>
          </div>
        </button>

      </div>


      <!-- INPUT -->

      <div class="ltc-inputbar">

        <input
          type="text"
          class="ltc-input"
          placeholder="Ask your travel question..."
          maxlength="1000"
          autocomplete="off"
          disabled
        />

        <button
          class="ltc-send"
          disabled
        >
          <span>➤</span>
        </button>

      </div>


      <!-- FOOTER -->

      <div class="ltc-footer">

        <span>
          AI travel guidance
        </span>

        <a
          class="ltc-escalate"
          href="https://wa.me/REPLACE_WITH_REAL_NUMBER"
          target="_blank"
          rel="noopener noreferrer"
        >
          Talk to a consultant
        </a>

      </div>

    </div>
  `;


  document.body.appendChild(root);


  /* =========================================================
     ELEMENT REFERENCES
     ========================================================= */

  const fab =
    root.querySelector(".ltc-fab");

  const panel =
    root.querySelector(".ltc-panel");

  const closeBtn =
    root.querySelector(".ltc-close");

  const messagesEl =
    root.querySelector(".ltc-messages");

  const input =
    root.querySelector(".ltc-input");

  const sendBtn =
    root.querySelector(".ltc-send");

  const suggestedButtons =
    root.querySelectorAll(".ltc-suggested button");


  /* =========================================================
     OPEN CHAT
     ========================================================= */

  fab.addEventListener("click", () => {

    panel.hidden = !panel.hidden;

    if (!panel.hidden) {

      if (!sessionId) {
        initSession();
      } else {
        input.focus();
      }

    }

  });


  /* =========================================================
     CLOSE
     ========================================================= */

  closeBtn.addEventListener("click", () => {

      panel.setAttribute('hidden', '');

  });

  /* =========================================================
     QUICK QUESTIONS
     ========================================================= */

  suggestedButtons.forEach((button) => {

    button.addEventListener("click", () => {

      const question =
        button.dataset.q;

      if (
        sessionReady &&
        !busy
      ) {

        sendMessage(question);

      }

    });

  });


  /* =========================================================
     SEND BUTTON
     ========================================================= */

  sendBtn.addEventListener("click", () => {

    sendCurrentMessage();

  });


  /* =========================================================
     ENTER
     ========================================================= */

  input.addEventListener("keydown", (event) => {

    if (event.key === "Enter") {

      event.preventDefault();

      sendCurrentMessage();

    }

  });


  function sendCurrentMessage() {

    const text =
      input.value.trim();

    if (
      text &&
      sessionReady &&
      !busy
    ) {

      sendMessage(text);

    }

  }


  /* =========================================================
     ENABLE / DISABLE CONTROLS
     ========================================================= */

  function setBusy(value) {

    busy = value;

    const enabled =
      sessionReady && !busy;

    input.disabled = !enabled;

    sendBtn.disabled = !enabled;

    suggestedButtons.forEach(
      button => {
        button.disabled = !enabled;
      }
    );


    if (!sessionReady) {

      input.placeholder =
        "Connecting to Travel Assistant...";

    } else if (busy) {

      input.placeholder =
        "Travel Assistant is thinking...";

    } else {

      input.placeholder =
        "Ask your travel question...";

    }

  }


  /* =========================================================
     ADD AI / USER MESSAGE
     ========================================================= */

  function addMessage(role, text) {

    const bubble =
      document.createElement("div");

    bubble.className =
      `ltc-bubble ltc-${role}`;

    bubble.textContent =
      text;

    messagesEl.appendChild(bubble);

    messagesEl.scrollTop =
      messagesEl.scrollHeight;

    return bubble;

  }


  /* =========================================================
     TYPING INDICATOR
     ========================================================= */

  function addTypingIndicator() {

    const bubble =
      document.createElement("div");

    bubble.className =
      "ltc-bubble ltc-bot ltc-typing";

    bubble.innerHTML = `
      <span class="ltc-dot"></span>
      <span class="ltc-dot"></span>
      <span class="ltc-dot"></span>
    `;

    messagesEl.appendChild(bubble);

    messagesEl.scrollTop =
      messagesEl.scrollHeight;

    return bubble;

  }


  /* =========================================================
     CREATE SESSION
     ========================================================= */

  async function initSession() {

    setBusy(true);

    try {

      const res =
        await fetch(
          `${API_BASE}/api/session`,
          {
            method: "POST"
          }
        );


      if (!res.ok) {

        throw new Error(
          "session create failed"
        );

      }


      const data =
        await res.json();


      sessionId =
        data.session_id;

      sessionReady = true;


      /*
       * DO NOT add another welcome message here.
       * The welcome UI already exists in the markup.
       */


    } catch (error) {

      console.error(
        "Session error:",
        error
      );


      addMessage(
        "bot",
        "Sorry, I couldn't connect right now. Please refresh and try again."
      );

    } finally {

      setBusy(false);

      if (sessionReady) {
        input.focus();
      }

    }

  }


  /* =========================================================
     SEND MESSAGE TO YOUR EXISTING BACKEND
     ========================================================= */

  async function sendMessage(text) {

    if (
      !sessionReady ||
      busy
    ) {

      return;

    }


    /*
     * USER MESSAGE
     */

    addMessage(
      "user",
      text
    );


    input.value = "";

    setBusy(true);


    /*
     * AI TYPING
     */

    const typing =
      addTypingIndicator();


    try {

      /*
       * YOUR ORIGINAL API CALL
       */

      const res =
        await fetch(
          `${API_BASE}/api/chat`,
          {
            method: "POST",

            headers: {
              "Content-Type":
                "application/json"
            },

            body: JSON.stringify({

              session_id:
                sessionId,

              message:
                text,

              language:
                "auto"

            })

          }
        );


      typing.remove();


      /* =====================================================
         ERROR RESPONSES
         ===================================================== */

      if (!res.ok) {

        if (res.status === 429) {

          addMessage(
            "bot",
            "Please wait for the previous reply before sending another message."
          );

        } else if (res.status === 504) {

          addMessage(
            "bot",
            "That took too long to answer. Please try again."
          );

        } else {

          addMessage(
            "bot",
            "Sorry, something went wrong. Please try again or contact us via WhatsApp."
          );

        }

        return;

      }


      /* =====================================================
         AI RESPONSE
         ===================================================== */

      const data =
        await res.json();


      addMessage(
        "bot",
        data.reply
      );


      /* =====================================================
         ESCALATION
         ===================================================== */

      if (data.escalate) {

        addMessage(
          "bot",
          "For personalized assistance, you can also contact our human travel consultant through WhatsApp."
        );

      }


        } catch (error) {

      typing.remove();


      console.error(
        "Chat error:",
        error
      );


      addMessage(
        "bot",
        "Sorry, something went wrong. Please try again or contact us via WhatsApp."
      );


    } finally {

      setBusy(false);

      input.focus();

    }

  }

})();

