using UnityEngine;
using NativeWebSocket;
using System;
using System.Text;
using System.Threading.Tasks;

public class WebSocketManager : MonoBehaviour
{
    [Header("Network Settings")]
    [SerializeField] private string ip = "127.0.0.1";
    [SerializeField] private string port = "8080";

    [Header("Debug")]
    [SerializeField] private bool showDebug = true;
    private string serverUrl = "";
    
    private WebSocket websocket;

    // A public property to check if the socket is ready to send data
    public bool IsConnected => websocket != null && websocket.State == WebSocketState.Open;

    private async void Start()
    {
        serverUrl = $"ws://{ip}:{port}";
        websocket = new WebSocket(serverUrl);

        websocket.OnOpen += () => Debug.Log("[NetworkManager] Relay server connected successfully.");
        
        websocket.OnMessage += (bytes) => 
        {
            string jsonText = Encoding.UTF8.GetString(bytes);
            if(showDebug) Debug.Log($"[NetworkManager] Subtitle received from server: {jsonText}");
        };
        
        websocket.OnError += (e) => Debug.LogError($"[NetworkManager] WebSocket Error: {e}");

        // Attempt to connect without blocking the main thread completely
        _ = ConnectToServer();
    }

    private async Task ConnectToServer()
    {
        try
        {
            await websocket.Connect();
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[NetworkManager] Cannot connect to relay server. Make sure the server is running. Error: {e.Message}");
        }
    }

    private void Update()
    {
        #if !UNITY_WEBGL
        if (websocket != null)
        {
            websocket.DispatchMessageQueue();
        }
        #endif
    }

    /// <summary>
    /// Public method to allow other scripts to send byte arrays through the websocket.
    /// </summary>
    public void SendAudioData(byte[] pcmData)
    {
        if (IsConnected)
        {
            websocket.Send(pcmData);
        }
    }

    private async void OnApplicationQuit() 
    {
        if (websocket != null) 
        {
            await websocket.Close();
        }
    }
}