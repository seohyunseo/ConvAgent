using UnityEngine;
using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine.UI;

public class AudioManager : MonoBehaviour
{
    [Header("Dependencies")]
    [Tooltip("Drag and drop the GameObject with WebSocketManager here.")]
    [SerializeField] private WebSocketManager webSocketManager;

    [Header("Audio Settings")]
    [SerializeField] private int sampleRate = 48000;
    [SerializeField] private int bufferLengthSeconds = 10;
    [SerializeField] private Slider gainSlider;
    
    [Header("Debug")]
    [SerializeField] private bool showDebug = true;
    [SerializeField] private TextMeshProUGUI gainValue;

    private AudioClip micClip;
    private int lastPosition = 0;
    private float volume_multiplier = 1f;

    private void Start()
    {
        gainSlider.onValueChanged.AddListener(OnGainChanged);

#if UNITY_ANDROID && !UNITY_EDITOR
        RequestMicrophonePermission();
#else
        InitializeMicrophone();
#endif
    }

#if UNITY_ANDROID && !UNITY_EDITOR
    private void RequestMicrophonePermission()
    {
        if (UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Microphone))
        {
            // Permission already granted — initialize immediately
            InitializeMicrophone();
            return;
        }

        // Build callbacks so we only initialize after the user grants access
        var callbacks = new UnityEngine.Android.PermissionCallbacks();
        callbacks.PermissionGranted += OnMicPermissionGranted;
        callbacks.PermissionDenied += OnMicPermissionDenied;
        callbacks.PermissionDeniedAndDontAskAgain += OnMicPermissionDenied;

        UnityEngine.Android.Permission.RequestUserPermission(
            UnityEngine.Android.Permission.Microphone, callbacks);
    }

    private void OnMicPermissionGranted(string permissionName)
    {
        Debug.Log("[AudioManager] Microphone permission granted.");
        InitializeMicrophone();
    }

    private void OnMicPermissionDenied(string permissionName)
    {
        Debug.LogError("[AudioManager] Microphone permission denied. Audio capture will not work.");
    }
#endif

    private void InitializeMicrophone()
    {
        if (Microphone.devices.Length > 0)
        {
            Debug.Log("[AudioManager] === Connected Microphone List ===");
            for (int i = 0; i < Microphone.devices.Length; i++)
            {
                Debug.Log($"[{i}] {Microphone.devices[i]}");
            }
            
            Debug.Log($"[AudioManager] Currently assigned default microphone (null input): {Microphone.devices[0]}");
            Debug.Log("========================================");
        }
        else
        {
            Debug.LogError("[AudioManager] No microphone connected to the system!");
            return;
        }

        micClip = Microphone.Start(null, true, bufferLengthSeconds, sampleRate);
        Debug.Log("[AudioManager] Microphone recording started.");
    }

    private void Update()
    {
        // 1. Ensure network is ready and mic is capturing
        if (webSocketManager == null || !webSocketManager.IsConnected || micClip == null) return;

        int currentPosition = Microphone.GetPosition(null);
        if (currentPosition <= 0 || lastPosition == currentPosition) return;

        // 2. Calculate accumulated buffer length
        int length = currentPosition - lastPosition;
        if (length < 0) length += micClip.samples; // Adjust length if wrap-around (loop) occurs

        // 3. Optimization: Wait until at least 0.1 seconds of audio (1600 samples) is collected
        if (length == 0 || length < 4800) return;

        float[] samples = new float[length];

        // 4. Wrap-around safety processing
        if (currentPosition < lastPosition)
        {
            // The record position wrapped around to the beginning of the buffer.
            // We need to read the tail part and the head part separately.
            int tailLength = micClip.samples - lastPosition;

            if (tailLength > 0)
            {
                float[] tailSamples = new float[tailLength];
                micClip.GetData(tailSamples, lastPosition);
                Array.Copy(tailSamples, 0, samples, 0, tailLength);
            }

            if (currentPosition > 0)
            {
                float[] headSamples = new float[currentPosition];
                micClip.GetData(headSamples, 0);
                Array.Copy(headSamples, 0, samples, tailLength, currentPosition);
            }
        }
        else
        {
            // Normal sequential reading
            micClip.GetData(samples, lastPosition);
        }
        
        lastPosition = currentPosition;
        
        // 5. Debugging visualizer
        if (showDebug)
        {
            DebugAudioLevel(samples);
        }
        
        // 6. Convert to PCM and send via WebSocketManager
        byte[] pcmBytes = ConvertToPcm16(samples);
        webSocketManager.SendAudioData(pcmBytes); 
    }

    private float GetDecibel(float[] samples)
    {
        if (samples.Length == 0) return -120;

        float sum = 0f;
        for (int i = 0; i < samples.Length; i++)
        {
            sum += samples[i] * samples[i];
        }
        
        // Calculate RMS (Root Mean Square) to evaluate volume
        float rms = Mathf.Sqrt(sum / samples.Length);
        
        // Convert to decibels (-60dB to 0dB)
        float db = 20 * Mathf.Log10(rms > 0 ? rms : 0.0001f); 

        return db;
    }

    private void DebugAudioLevel(float[] samples)
    {
        float db = GetDecibel(samples);

        // Filter out silence (below -60dB)
        if (db < -60f) return;

        // Visual bar graph output in console (e.g., [???????--------] -23.4 dB)
        int barLength = Mathf.Clamp(Mathf.RoundToInt((db + 60f) / 2f), 0, 30);
        string bar = new string('?', barLength).PadRight(30, '-');
        
        Debug.Log($"[AudioManager] MIC Vol: [{bar}] {db:F1} dB");
    }

    private byte[] ConvertToPcm16(float[] samples) 
    {
        // float db = GetDecibel(samples);

        // if (db < -45f) 
        // {
        //     // Array.Clear(samples, 0, samples.Length); 
        //     for (int i = 0; i < samples.Length; i++)
        //     {
        //         samples[i] *= 0.01f; 
        //     }
        // }

        byte[] pcmData = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++) 
        {
            short shortSample = (short)(Mathf.Clamp(samples[i]*volume_multiplier, -1f, 1f) * 32767);
            pcmData[i * 2] = (byte)(shortSample & 0xFF);
            pcmData[i * 2 + 1] = (byte)((shortSample >> 8) & 0xFF);
        }
        return pcmData;
    }

    private void OnApplicationQuit() 
    {
        if (micClip != null) 
        {
            Microphone.End(null); // Release microphone resource on exit
        }
    }

    public void OnGainChanged(float value){
        volume_multiplier = value;
        gainValue.text = volume_multiplier.ToString("F2");
    }
}
