using UnityEngine;
using TMPro;

[System.Serializable] // 필수! JsonUtility가 읽을 수 있게 해줌
public class JSONData
{
    public string entity; 
    public string description; 

}

public class DisplayManager : MonoBehaviour
{
    [Header("Dependencies")]
    [Tooltip("Drag and drop the GameObject with WebSocketManager here.")]
    [SerializeField] private WebSocketManager webSocketManager;

    [Header("UI Settings")]
    [SerializeField] private TextMeshProUGUI debugText;
    
    private void OnEnable()
    {
        // WebSocketManager가 활성화되어 있다면 이벤트를 구독합니다.
        if (webSocketManager != null)
        {
            webSocketManager.OnMessageReceived += HandleOnMessageReceived;
        }
    }

    private void OnDisable()
    {
        // 메모리 누수 방지를 위해 오브젝트가 비활성화되거나 파괴될 때 반드시 구독을 해제합니다.
        if (webSocketManager != null)
        {
            webSocketManager.OnMessageReceived -= HandleOnMessageReceived;
        }
    }

    private void HandleOnMessageReceived(string jsonText)
    {
        try
        {
            Debug.Log($"[UIManager] Handling Message: {jsonText}");
            JSONData data = JsonUtility.FromJson<JSONData>(jsonText);
            debugText.text = $"{data.entity}: {data.description}";
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[SubtitleDisplay] JSON 파싱 중 에러 발생: {e.Message}");
        }
    }
}
