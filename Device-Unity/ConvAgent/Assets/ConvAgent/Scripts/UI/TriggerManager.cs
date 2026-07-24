using UnityEngine;

public class TriggerManager : MonoBehaviour
{
    [Header("Dependencies")]
    [Tooltip("Drag and drop the GameObject with WebSocketManager here.")]
    [SerializeField] private WebSocketManager webSocketManager;

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space))
        {
            webSocketManager.SendTextData("trigger LLM");
        }
    }
}
