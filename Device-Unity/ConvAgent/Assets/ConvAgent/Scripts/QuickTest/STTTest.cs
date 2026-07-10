using UnityEngine;
using NativeWebSocket;
using System;

public class STTTest : MonoBehaviour
{
    private WebSocket websocket;
    private AudioClip micClip;
    private int lastPosition = 0;
    private const int SampleRate = 16000;

    [Header("Debug")]
    public bool showAudioLevelDebug = true; // 인스펙터에서 켜고 끌 수 있습니다.

    async void Start()
    {
        // 마이크 권한 확인 (Quest 3 필수)
#if UNITY_ANDROID && !UNITY_EDITOR
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Microphone))
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.Microphone);
#endif

        if (Microphone.devices.Length > 0)
        {
            Debug.Log("[STT] === 연결된 마이크 목록 ===");
            for (int i = 0; i < Microphone.devices.Length; i++)
            {
                Debug.Log($"[{i}] {Microphone.devices[i]}");
            }
            
            // Microphone.Start에 null을 넣었을 때 유니티가 강제로 선택하는 '기본 마이크'
            Debug.Log($"[STT]현재 할당된 기본 마이크(null 입력 시): {Microphone.devices[0]}");
            Debug.Log("===============================");
        }
        else
        {
            Debug.LogError("[STT] 시스템에 연결된 마이크가 단 하나도 없습니다!");
        }


        micClip = Microphone.Start(null, true, 10, SampleRate);
        Debug.Log("[STT] 마이크 녹음 시작됨");

        websocket = new WebSocket("ws://127.0.0.1:8080");

        websocket.OnOpen += () => Debug.Log("[STT] 중계 서버 오픈");
        websocket.OnMessage += (bytes) => {
            string jsonText = System.Text.Encoding.UTF8.GetString(bytes);
            Debug.Log($"[STT] 서버 수신 자막: {jsonText}");
        };
        websocket.OnError += (e) => Debug.LogError($"[STT] 웹소켓 에러: {e}");

        try
        {
            await websocket.Connect();
            Debug.Log("[STT] 중계 서버 연결 성공");
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[STT] 중계 서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요. 에러: {e.Message}");
        }

        
    }

    void Update()
    {
        #if !UNITY_WEBGL
        if (websocket != null) websocket.DispatchMessageQueue();
        #endif

        if (websocket == null || websocket.State != WebSocketState.Open || micClip == null) return;

        int currentPosition = Microphone.GetPosition(null);
        if (currentPosition <= 0 || lastPosition == currentPosition) return;

        // 1. 버퍼 길이 계산
        int length = currentPosition - lastPosition;
        if (length < 0) length += micClip.samples; // 루프 발생 시 길이 보정

        if(length == 0 || length < 1600) return;

        
        float[] samples = new float[length];

        // 2. ? 루프(Wrap-around) 안전 처리
        if (currentPosition < lastPosition)
        {
            // 배열의 끝을 넘어간 경우: 끝부분과 처음부분을 두 번 나누어 읽습니다.
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
            // 일반적인 경우
            micClip.GetData(samples, lastPosition);
        }
        
        lastPosition = currentPosition;
        
        // 3. 디버그: 오디오 데이터가 제대로 들어오는지 확인
        if (showAudioLevelDebug)
        {
            DebugAudioLevel(samples);
        }

        
        // 4. PCM 변환 및 서버 전송
        byte[] pcmBytes = ConvertToPcm16(samples);
        websocket.Send(pcmBytes); 
    }

    // ==========================================
    // ? 오디오 디버깅용 함수
    // ==========================================
    private void DebugAudioLevel(float[] samples)
    {

        if (samples.Length == 0) return;

        float sum = 0f;
        for (int i = 0; i < samples.Length; i++)
        {
            sum += samples[i] * samples[i];
        }
        
        // RMS (Root Mean Square) 계산하여 소리의 크기 파악
        float rms = Mathf.Sqrt(sum / samples.Length);
        
        // 데시벨(dB) 변환 (-60dB ~ 0dB 사이)
        float db = 20 * Mathf.Log10(rms > 0 ? rms : 0.0001f); 

        // 침묵 상태(-60dB 이하) 필터링
        if (db < -60f) return;

        // 콘솔에 시각적 막대그래프 출력 (예: [???????--------] -23.4 dB)
        int barLength = Mathf.Clamp(Mathf.RoundToInt((db + 60f) / 2f), 0, 30);
        string bar = new string('?', barLength).PadRight(30, '-');
        
        Debug.Log($"[STT] MIC Vol: [{bar}] {db:F1} dB");
    }

    private byte[] ConvertToPcm16(float[] samples) {
        byte[] pcmData = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++) {
            short shortSample = (short)(Mathf.Clamp(samples[i], -1f, 1f) * 32767);
            byte[] byteSample = BitConverter.GetBytes(shortSample);
            pcmData[i * 2] = byteSample[0];
            pcmData[i * 2 + 1] = byteSample[1];
        }
        return pcmData;
    }

    async void OnApplicationQuit() {
        if (micClip != null) Microphone.End(null); // 앱 종료 시 마이크 반환
        if (websocket != null) await websocket.Close();
    }
}