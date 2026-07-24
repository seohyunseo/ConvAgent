using UnityEngine;
using System.Net.WebSockets;
using System.Net.Sockets;
using System.Security.Cryptography;
using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Concurrent;
using TMPro;

public class WebSocketManager : MonoBehaviour
{
    // ──────────────────────────────────────────────────────────
    // Inspector References
    // ──────────────────────────────────────────────────────────

    [Header("Network Settings")]
    [SerializeField] private string ip = "127.0.0.1";
    [SerializeField] private string port = "8080";
    [SerializeField] private TMP_InputField ipInput;
    [SerializeField] private TMP_InputField portInput;

    [HideInInspector]
    public event Action<string> OnMessageReceived;

    [Header("Debug")]
    [SerializeField] private bool showDebug = true;

    // ──────────────────────────────────────────────────────────
    // Private State
    // ──────────────────────────────────────────────────────────

    private string serverUrl = "";

    // WebSocket base class — created via WebSocket.CreateFromStream() so we can
    // control the underlying TCP socket settings (NoDelay, etc.).
    private WebSocket websocket;

    // The raw TCP connection kept alive for the lifetime of the WebSocket.
    // TcpClient.NoDelay = true disables Nagle's algorithm, ensuring every
    // SendAsync call is flushed to the network immediately on Android/Mono.
    private TcpClient m_TcpClient;

    // Single CancellationTokenSource for both the send loop and receive loop.
    private CancellationTokenSource m_Cts;

    // Outgoing queue: binary audio or UTF-8 text payloads.
    // WebSocket only allows ONE concurrent SendAsync — the SendLoop enforces that.
    private readonly ConcurrentQueue<(byte[] data, WebSocketMessageType type)> m_SendQueue
        = new ConcurrentQueue<(byte[], WebSocketMessageType)>();

    // Incoming queue: messages received on the background ReceiveLoop thread
    // are posted here and dispatched to the Unity main thread in Update().
    private readonly ConcurrentQueue<string> m_ReceiveQueue
        = new ConcurrentQueue<string>();

    // ──────────────────────────────────────────────────────────
    // Public State
    // ──────────────────────────────────────────────────────────

    public bool IsConnected => websocket != null && websocket.State == WebSocketState.Open;

    // ──────────────────────────────────────────────────────────
    // Connection
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Reads IP/port from the Inspector input fields (if assigned),
    /// then creates a raw TcpClient with NoDelay, performs the WebSocket
    /// handshake manually, and kicks off the I/O loops.
    /// </summary>
    private void InitializeWebSocket()
    {
        if (ipInput   != null) ip   = ipInput.text;
        if (portInput != null) port = portInput.text;

        serverUrl = $"ws://{ip}:{port}";

        CleanupWebSocket();

        m_Cts = new CancellationTokenSource();
        _ = ConnectAndRunAsync(m_Cts.Token);
    }

    private async Task ConnectAndRunAsync(CancellationToken ct)
    {
        try
        {
            Uri uri  = new Uri(serverUrl);
            string host    = uri.Host;
            int    tcpPort = uri.Port < 0 ? 80 : uri.Port;
            string path    = string.IsNullOrEmpty(uri.PathAndQuery) ? "/" : uri.PathAndQuery;

            // ── Step 1: Open a raw TCP socket with Nagle disabled ────────────────
            // This is the key fix for Android/Mono: ClientWebSocket wraps the socket in a
            // BufferedStream, causing writes to be held until the buffer fills or the
            // connection closes. By building the WebSocket on top of our own TcpClient
            // (NoDelay = true), every SendAsync call writes through to the OS socket
            // immediately — no buffering, no delayed delivery on Meta Quest.
            m_TcpClient = new TcpClient();
            m_TcpClient.NoDelay = true;

            await m_TcpClient.ConnectAsync(host, tcpPort);
            NetworkStream stream = m_TcpClient.GetStream();

            // ── Step 2: Perform the WebSocket HTTP Upgrade handshake ─────────────
            await PerformHandshakeAsync(stream, host, tcpPort, path, ct);

            // ── Step 3: Wrap the upgraded stream in a proper WebSocket ────────────
            // isServer: false → outgoing frames are masked (RFC 6455 client requirement).
            websocket = WebSocket.CreateFromStream(
                stream,
                isServer:          false,
                subProtocol:       null,
                keepAliveInterval: TimeSpan.FromSeconds(30));

            Debug.Log("[NetworkManager] Relay server connected successfully.");

            // ── Step 4: Run send/receive loops concurrently ───────────────────────
            Task sendTask    = SendLoop(ct);
            Task receiveTask = ReceiveLoop(ct);

            await Task.WhenAny(sendTask, receiveTask);
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown — nothing to report.
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[NetworkManager] Connection failed. Make sure the server is running. Error: {e.Message}");
        }
    }

    /// <summary>
    /// Sends the HTTP/1.1 Upgrade request and reads the 101 response,
    /// leaving the stream ready for WebSocket frames.
    /// </summary>
    private async Task PerformHandshakeAsync(
        NetworkStream stream, string host, int port, string path, CancellationToken ct)
    {
        // Generate a cryptographically random 16-byte WebSocket key (RFC 6455 §4.1).
        byte[] keyBytes = new byte[16];
        using (var rng = RandomNumberGenerator.Create())
            rng.GetBytes(keyBytes);
        string wsKey = Convert.ToBase64String(keyBytes);

        // Build the HTTP Upgrade request.
        string request =
            $"GET {path} HTTP/1.1\r\n" +
            $"Host: {host}:{port}\r\n" +
            "Upgrade: websocket\r\n" +
            "Connection: Upgrade\r\n" +
            $"Sec-WebSocket-Key: {wsKey}\r\n" +
            "Sec-WebSocket-Version: 13\r\n" +
            "\r\n";

        byte[] requestBytes = Encoding.ASCII.GetBytes(request);
        await stream.WriteAsync(requestBytes, 0, requestBytes.Length, ct);

        // Read the server's HTTP response until we see the header terminator.
        byte[] buffer    = new byte[4096];
        int    totalRead = 0;

        while (totalRead < buffer.Length)
        {
            int read = await stream.ReadAsync(buffer, totalRead, buffer.Length - totalRead, ct);
            if (read == 0) throw new Exception("Server closed the connection during WebSocket handshake.");
            totalRead += read;

            string partial = Encoding.UTF8.GetString(buffer, 0, totalRead);
            if (partial.Contains("\r\n\r\n")) break;
        }

        string response = Encoding.UTF8.GetString(buffer, 0, totalRead);

        if (!response.Contains("101 Switching Protocols"))
            throw new Exception($"WebSocket upgrade rejected. Server response:\n{response}");

        Debug.Log("[NetworkManager] WebSocket handshake complete.");
    }

    // ──────────────────────────────────────────────────────────
    // Background I/O Loops
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Continuously reads incoming WebSocket frames on a background thread.
    /// Complete text messages are pushed to m_ReceiveQueue for main-thread dispatch.
    /// </summary>
    private async Task ReceiveLoop(CancellationToken ct)
    {
        byte[] buffer = new byte[8192];

        while (!ct.IsCancellationRequested && IsConnected)
        {
            try
            {
                var segment = new ArraySegment<byte>(buffer);
                WebSocketReceiveResult result = await websocket.ReceiveAsync(segment, ct);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[NetworkManager] Server closed the connection.");
                    break;
                }

                if (result.MessageType == WebSocketMessageType.Text)
                {
                    string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    m_ReceiveQueue.Enqueue(message);
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception e)
            {
                Debug.LogError($"[NetworkManager] WebSocket Receive Error: {e.Message}");
                break;
            }
        }
    }

    /// <summary>
    /// Drains the send queue one message at a time.
    /// WebSocket only allows one concurrent SendAsync — this loop guarantees that.
    /// </summary>
    private async Task SendLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && IsConnected)
        {
            if (m_SendQueue.TryDequeue(out var item))
            {
                try
                {
                    await websocket.SendAsync(
                        new ArraySegment<byte>(item.data),
                        item.type,
                        endOfMessage:      true,
                        cancellationToken: ct);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception e)
                {
                    Debug.LogWarning($"[NetworkManager] Send failed: {e.Message}");
                }
            }
            else
            {
                // Nothing queued — yield for 1 ms to avoid busy-spinning.
                await Task.Delay(1, ct).ContinueWith(_ => { }); // swallow OperationCancelled
            }
        }
    }

    // ──────────────────────────────────────────────────────────
    // Unity Lifecycle
    // ──────────────────────────────────────────────────────────

    private void Update()
    {
        // Dispatch messages received on the background thread to Unity main thread.
        while (m_ReceiveQueue.TryDequeue(out string jsonText))
        {
            if (showDebug)
                Debug.Log($"[NetworkManager] Message received from server: {jsonText}");

            OnMessageReceived?.Invoke(jsonText);
        }

#if UNITY_EDITOR
        if (Input.GetKeyDown(KeyCode.C))
            InitializeWebSocket();
#endif
    }

    private async void OnApplicationQuit()
    {
        await DisconnectAsync();
    }

    // ──────────────────────────────────────────────────────────
    // Public Send API
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Enqueues binary PCM data for sending. Non-blocking; the SendLoop dispatches it.
    /// </summary>
    public void SendAudioData(byte[] pcmData)
    {
        if (pcmData == null || pcmData.Length == 0) return;
        m_SendQueue.Enqueue((pcmData, WebSocketMessageType.Binary));
    }

    /// <summary>
    /// Enqueues a UTF-8 text message for sending. Non-blocking.
    /// </summary>
    public void SendTextData(string message)
    {
        if (string.IsNullOrEmpty(message)) return;
        m_SendQueue.Enqueue((Encoding.UTF8.GetBytes(message), WebSocketMessageType.Text));
    }

    // ──────────────────────────────────────────────────────────
    // UI Button Handlers
    // ──────────────────────────────────────────────────────────

    public void OnIPEdit(string newIp)     => ip   = newIp;
    public void OnPortEdit(string newPort) => port = newPort;

    public void OnConnectButtonClicked()          => InitializeWebSocket();
    public async void OnDisconnectButtonClicked() => await DisconnectAsync();

    // ──────────────────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Graceful disconnect: cancel loops → WebSocket close handshake → dispose.
    /// </summary>
    private async Task DisconnectAsync()
    {
        m_Cts?.Cancel();

        if (websocket != null && websocket.State == WebSocketState.Open)
        {
            try
            {
                await websocket.CloseAsync(
                    WebSocketCloseStatus.NormalClosure,
                    "Closing",
                    CancellationToken.None);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[NetworkManager] Error during WebSocket close: {e.Message}");
            }
        }

        websocket?.Dispose();
        websocket = null;

        m_TcpClient?.Close();
        m_TcpClient?.Dispose();
        m_TcpClient = null;
    }

    /// <summary>
    /// Immediate teardown without a close handshake — used before reinitialising.
    /// </summary>
    private void CleanupWebSocket()
    {
        m_Cts?.Cancel();

        websocket?.Dispose();
        websocket = null;

        m_TcpClient?.Close();
        m_TcpClient?.Dispose();
        m_TcpClient = null;
    }
}