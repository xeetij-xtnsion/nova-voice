/**
 * Nova Voice AI — WebRTC client for OpenAI Realtime API
 *
 * Flow:
 * 1. Fetch ephemeral token from /api/session
 * 2. Establish WebRTC connection with OpenAI
 * 3. Handle voice I/O via audio tracks
 * 4. Relay function calls to our server via data channel
 * 5. Log conversation turns to shared analytics DB
 */

let peerConnection = null;
let dataChannel = null;
let audioElement = null;
let voiceSessionId = null;

// ── UI helpers ──────────────────────────────────────────────────────

function setStatus(state, text) {
    const dot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    dot.className = "status-dot " + state;
    statusText.textContent = text;
}

function showStartBtn() {
    document.getElementById("startBtn").style.display = "";
    document.getElementById("endBtn").style.display = "none";
}

function showEndBtn() {
    document.getElementById("startBtn").style.display = "none";
    document.getElementById("endBtn").style.display = "";
}

function clearTranscript() {
    document.getElementById("transcript").innerHTML = "";
}

function addMessage(role, text) {
    const transcript = document.getElementById("transcript");
    // Remove empty state if present
    const empty = transcript.querySelector(".transcript-empty");
    if (empty) empty.remove();

    const msg = document.createElement("div");
    msg.className = "message " + role;

    const label = document.createElement("div");
    label.className = "label";
    label.textContent = role === "user" ? "You" : "Nova";

    const content = document.createElement("div");
    content.textContent = text;

    msg.appendChild(label);
    msg.appendChild(content);
    transcript.appendChild(msg);
    transcript.scrollTop = transcript.scrollHeight;

    return content;
}

function addToolIndicator(toolName) {
    const transcript = document.getElementById("transcript");
    const indicator = document.createElement("div");
    indicator.className = "tool-indicator";
    indicator.textContent = `Looking up ${toolName.replace(/_/g, " ")}...`;
    transcript.appendChild(indicator);
    transcript.scrollTop = transcript.scrollHeight;
    return indicator;
}

// Track the current streaming assistant message
let currentAssistantContent = null;
let currentAssistantText = "";

// Track the last user transcript for conversation logging
let lastUserTranscript = "";

// ── Start conversation ──────────────────────────────────────────────

async function startConversation() {
    try {
        setStatus("connecting", "Connecting...");
        document.getElementById("startBtn").disabled = true;

        // 1. Get ephemeral token from our server
        const sessionRes = await fetch("/api/session");
        const sessionData = await sessionRes.json();

        if (sessionData.error) {
            throw new Error(sessionData.detail || "Failed to create session");
        }

        const ephemeralKey = sessionData.client_secret.value;
        voiceSessionId = sessionData.voice_session_id;

        // 2. Create WebRTC peer connection
        peerConnection = new RTCPeerConnection();

        // 3. Set up audio playback for AI responses
        audioElement = document.createElement("audio");
        audioElement.autoplay = true;
        peerConnection.ontrack = (event) => {
            audioElement.srcObject = event.streams[0];
        };

        // 4. Get user microphone and add to connection
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });
        stream.getTracks().forEach((track) => {
            peerConnection.addTrack(track, stream);
        });

        // 5. Create data channel for events
        dataChannel = peerConnection.createDataChannel("oai-events");
        dataChannel.onopen = () => {
            setStatus("connected", "Connected — speak to Nova");
            showEndBtn();
        };
        dataChannel.onmessage = handleDataChannelMessage;
        dataChannel.onclose = () => {
            setStatus("", "Disconnected");
            showStartBtn();
        };

        // 6. Create SDP offer and connect to OpenAI
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);

        const sdpRes = await fetch(
            `https://api.openai.com/v1/realtime?model=${sessionData.model}`,
            {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${ephemeralKey}`,
                    "Content-Type": "application/sdp",
                },
                body: offer.sdp,
            }
        );

        if (!sdpRes.ok) {
            throw new Error(`SDP exchange failed: ${sdpRes.status}`);
        }

        const answerSdp = await sdpRes.text();
        await peerConnection.setRemoteDescription({
            type: "answer",
            sdp: answerSdp,
        });

    } catch (err) {
        console.error("Failed to start conversation:", err);
        setStatus("error", "Error: " + err.message);
        showStartBtn();
        document.getElementById("startBtn").disabled = false;
    }
}

// ── End conversation ────────────────────────────────────────────────

function endConversation() {
    if (dataChannel) {
        dataChannel.close();
        dataChannel = null;
    }
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    if (audioElement) {
        audioElement.srcObject = null;
        audioElement = null;
    }
    currentAssistantContent = null;
    currentAssistantText = "";
    lastUserTranscript = "";
    voiceSessionId = null;
    setStatus("", "Disconnected");
    showStartBtn();
    document.getElementById("startBtn").disabled = false;
}

// ── Handle data channel messages ────────────────────────────────────

// Track pending function calls (call_id -> { name, arguments })
const pendingFunctionCalls = {};

function handleDataChannelMessage(event) {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
        // User's speech was transcribed
        case "conversation.item.input_audio_transcription.completed":
            if (msg.transcript && msg.transcript.trim()) {
                const text = msg.transcript.trim();
                addMessage("user", text);
                lastUserTranscript = text;
            }
            break;

        // Assistant started a new response — reset streaming state
        case "response.created":
            currentAssistantContent = null;
            currentAssistantText = "";
            break;

        // Streaming text from assistant
        case "response.audio_transcript.delta":
            if (msg.delta) {
                if (!currentAssistantContent) {
                    currentAssistantContent = addMessage("assistant", "");
                }
                currentAssistantText += msg.delta;
                currentAssistantContent.textContent = currentAssistantText;
                document.getElementById("transcript").scrollTop =
                    document.getElementById("transcript").scrollHeight;
            }
            break;

        // Assistant finished speaking — finalize and log
        case "response.audio_transcript.done":
            if (lastUserTranscript && currentAssistantText) {
                logConversation(lastUserTranscript, currentAssistantText);
            }
            currentAssistantContent = null;
            currentAssistantText = "";
            break;

        // Function call: accumulate arguments
        case "response.function_call_arguments.delta":
            if (msg.call_id) {
                if (!pendingFunctionCalls[msg.call_id]) {
                    pendingFunctionCalls[msg.call_id] = { name: "", args: "" };
                }
                pendingFunctionCalls[msg.call_id].args += msg.delta || "";
            }
            break;

        // Function call complete — relay to our server
        case "response.function_call_arguments.done":
            if (msg.call_id) {
                const callInfo = pendingFunctionCalls[msg.call_id] || {};
                callInfo.name = msg.name || callInfo.name;
                callInfo.args = msg.arguments || callInfo.args;
                handleFunctionCall(msg.call_id, callInfo.name, callInfo.args);
                delete pendingFunctionCalls[msg.call_id];
            }
            break;

        // Also capture the function call name from output_item
        case "response.output_item.added":
            if (msg.item && msg.item.type === "function_call") {
                const callId = msg.item.call_id;
                if (callId) {
                    pendingFunctionCalls[callId] = {
                        name: msg.item.name || "",
                        args: "",
                    };
                }
            }
            break;

        // Errors
        case "error":
            console.error("Realtime API error:", msg.error);
            setStatus("error", "Error: " + (msg.error?.message || "Unknown error"));
            break;
    }
}

// ── Relay function calls to our server ──────────────────────────────

async function handleFunctionCall(callId, functionName, argsString) {
    const indicator = addToolIndicator(functionName);

    try {
        const args = JSON.parse(argsString || "{}");

        // Map function names to our API endpoints
        let endpoint, body;
        if (functionName === "search_knowledge_base") {
            endpoint = "/api/tools/search_kb";
            body = { query: args.query };
        } else if (functionName === "get_clinic_info") {
            endpoint = "/api/tools/get_clinic_info";
            body = { topic: args.topic };
        } else if (functionName === "book_appointment") {
            endpoint = "/api/tools/book_appointment";
            body = {
                appointment_type: args.appointment_type,
                practitioner: args.practitioner,
                date: args.date,
                time: args.time,
                patient_name: args.patient_name,
                phone_number: args.phone_number,
                session_id: voiceSessionId,
            };
        } else {
            console.warn("Unknown function:", functionName);
            return;
        }

        // Call our server
        const res = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        const data = await res.json();
        const resultText = data.result || "No information available.";

        // Remove the "looking up..." indicator
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }

        // Send the result back to OpenAI via data channel
        // 1. Create a conversation item with the function output
        sendDataChannelEvent({
            type: "conversation.item.create",
            item: {
                type: "function_call_output",
                call_id: callId,
                output: resultText,
            },
        });

        // 2. Trigger the model to respond with the function result
        sendDataChannelEvent({
            type: "response.create",
        });

    } catch (err) {
        console.error("Function call error:", err);
        if (indicator && indicator.parentNode) {
            indicator.textContent = "Error looking up information";
        }

        // Send error result back so the model can recover gracefully
        sendDataChannelEvent({
            type: "conversation.item.create",
            item: {
                type: "function_call_output",
                call_id: callId,
                output: "Sorry, I had trouble looking that up. Please try asking again.",
            },
        });

        sendDataChannelEvent({
            type: "response.create",
        });
    }
}

function sendDataChannelEvent(event) {
    if (dataChannel && dataChannel.readyState === "open") {
        dataChannel.send(JSON.stringify(event));
    } else {
        console.warn("Data channel not open, cannot send event:", event.type);
    }
}

// ── Conversation logging ────────────────────────────────────────────

function logConversation(question, answer, routeTaken = "standard") {
    if (!voiceSessionId) return;

    fetch("/api/log_conversation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: voiceSessionId,
            question: question,
            answer: answer,
            route_taken: routeTaken,
            confidence: "high",
        }),
    }).catch((err) => console.warn("Failed to log conversation:", err));
}
