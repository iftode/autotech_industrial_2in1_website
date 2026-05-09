document.addEventListener("DOMContentLoaded", () => {
    const toggleBtn = document.querySelector("[data-nav-toggle]");
    const nav = document.querySelector("[data-nav]");

    if (toggleBtn && nav) {
        toggleBtn.addEventListener("click", () => {
            nav.classList.toggle("open");
        });
    }

    const chatToggle = document.querySelector("[data-chat-toggle]");
    const chatClose = document.querySelector("[data-chat-close]");
    const chatPanel = document.querySelector("[data-chat-panel]");
    const chatForm = document.querySelector("[data-chat-form]");
    const chatInput = document.querySelector("[data-chat-input]");
    const chatMessages = document.querySelector("[data-chat-messages]");

    function appendMessage(text, type = "bot") {
        if (!chatMessages) return;

        const message = document.createElement("div");
        message.className = `chat-msg ${type}`;
        message.innerHTML = text.replace(/\n/g, "<br>");
        chatMessages.appendChild(message);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function setChatOpen(open) {
        if (!chatPanel) return;
        if (open) {
            chatPanel.classList.add("open");
            if (chatInput) {
                setTimeout(() => chatInput.focus(), 100);
            }
        } else {
            chatPanel.classList.remove("open");
        }
    }

    if (chatToggle) {
        chatToggle.addEventListener("click", () => {
            const isOpen = chatPanel && chatPanel.classList.contains("open");
            setChatOpen(!isOpen);
        });
    }

    if (chatClose) {
        chatClose.addEventListener("click", () => {
            setChatOpen(false);
        });
    }

    if (chatForm) {
        chatForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            if (!chatInput) return;
            const text = chatInput.value.trim();
            if (!text) return;

            appendMessage(text, "user");
            chatInput.value = "";
            appendMessage("Se procesează...", "bot loading");

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ message: text })
                });

                const data = await response.json();

                const loadingMessage = chatMessages.querySelector(".chat-msg.loading:last-child");
                if (loadingMessage) {
                    loadingMessage.remove();
                }

                appendMessage(data.reply || "A apărut o eroare la procesarea mesajului.", "bot");
            } catch (error) {
                const loadingMessage = chatMessages.querySelector(".chat-msg.loading:last-child");
                if (loadingMessage) {
                    loadingMessage.remove();
                }

                appendMessage("A apărut o eroare. Te rugăm să încerci din nou.", "bot");
            }
        });
    }

    const paymentMethod = document.querySelector("[data-payment-method]");
    const cardFields = document.querySelector("[data-card-fields]");
    const cardHolder = document.querySelector("#card_holder");
    const cardNumber = document.querySelector("#card_number");
    const cardExpiry = document.querySelector("#card_expiry");
    const cardCvv = document.querySelector("#card_cvv");

    function toggleCardFields() {
        if (!paymentMethod || !cardFields) return;

        const show = paymentMethod.value === "card";
        cardFields.style.display = show ? "grid" : "none";

        if (cardHolder) {
            cardHolder.required = show;
            if (!show) cardHolder.value = "";
        }

        if (cardNumber) {
            cardNumber.required = show;
            if (!show) cardNumber.value = "";
        }

        if (cardExpiry) {
            cardExpiry.required = show;
            if (!show) cardExpiry.value = "";
        }

        if (cardCvv) {
            cardCvv.required = show;
            if (!show) cardCvv.value = "";
        }
    }

    if (paymentMethod && cardFields) {
        toggleCardFields();
        paymentMethod.addEventListener("change", toggleCardFields);
    }

    if (cardNumber) {
        cardNumber.addEventListener("input", () => {
            let value = cardNumber.value.replace(/\D/g, "").slice(0, 19);
            value = value.replace(/(.{4})/g, "$1 ").trim();
            cardNumber.value = value;
        });
    }

    if (cardExpiry) {
        cardExpiry.addEventListener("input", () => {
            let value = cardExpiry.value.replace(/\D/g, "").slice(0, 4);
            if (value.length >= 3) {
                value = value.slice(0, 2) + "/" + value.slice(2);
            }
            cardExpiry.value = value;
        });
    }

    if (cardCvv) {
        cardCvv.addEventListener("input", () => {
            cardCvv.value = cardCvv.value.replace(/\D/g, "").slice(0, 4);
        });
    }
});