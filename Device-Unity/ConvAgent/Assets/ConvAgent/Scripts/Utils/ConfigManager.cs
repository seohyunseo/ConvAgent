using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;
using System.Text;

/// <summary>
/// Captures Unity's Debug log output (all log types) and displays them
/// in a UI Scroll View using a single TextMeshProUGUI object.
/// Lines are colour-coded by log type via TMP rich-text tags.
///
/// UI Wiring (Inspector):
///   logText       → The single TextMeshProUGUI inside the Scroll View's Content
///   scrollRect    → The ScrollRect component on the Scroll View GameObject
///   clearButton   → Button that clears all displayed log lines
///   quitButton    → Button that hides this config canvas and shows the main canvas
///   configCanvas  → This config/debug canvas GameObject
///   mainCanvas    → The main canvas GameObject to restore on Quit
/// </summary>
public class ConfigManager : MonoBehaviour
{
    // ──────────────────────────────────────────────────────────
    // Inspector References
    // ──────────────────────────────────────────────────────────

    [Header("Log Scroll View")]
    [Tooltip("The single TextMeshProUGUI that displays all log lines.")]
    [SerializeField] private TextMeshProUGUI logText;

    [Tooltip("The ScrollRect component of the Scroll View.")]
    [SerializeField] private ScrollRect scrollRect;
    

    [Header("Controls")]
    [Tooltip("Button that clears all log lines from the display.")]
    [SerializeField] private Button clearButton;
    [SerializeField] private Button quitButton;

    [Header("Canvas")]
    [SerializeField] private GameObject configCanvas;
    [SerializeField] private GameObject mainCanvas;

    [Header("Display Settings")]
    [Tooltip("Maximum number of log lines kept before the oldest are trimmed.")]
    [SerializeField] private int maxLines = 200;

    // ──────────────────────────────────────────────────────────
    // Private State
    // ──────────────────────────────────────────────────────────

    // Accumulates each formatted log line.
    private readonly List<string> m_Lines = new List<string>();

    // Reusable StringBuilder to avoid GC pressure when rebuilding the full text.
    private readonly StringBuilder m_Builder = new StringBuilder();

    // Log-type to TMP rich-text colour mapping.
    private static readonly Dictionary<LogType, string> k_LogColour = new Dictionary<LogType, string>
    {
        { LogType.Log,       "#FFFFFF" },   // White  — normal log
        { LogType.Warning,   "#FFD700" },   // Gold   — warnings
        { LogType.Error,     "#FF4C4C" },   // Red    — errors
        { LogType.Assert,    "#FF4C4C" },   // Red    — assertions
        { LogType.Exception, "#FF4C4C" },   // Red    — exceptions
    };

    // ──────────────────────────────────────────────────────────
    // Unity Lifecycle
    // ──────────────────────────────────────────────────────────

    private void Awake()
    {
        // Allow the TMP text to grow beyond its initial rect size.
        // Without this, TMP silently clips (Truncate mode) once text exceeds the rect,
        // so new lines appear to stop showing even though .text is being updated.
        if (logText != null)
            logText.overflowMode = TextOverflowModes.Overflow;
    }

    private void OnEnable()
    {
        // Subscribe to Unity's global log event.
        Application.logMessageReceived += HandleLogReceived;

        if (clearButton != null)
            clearButton.onClick.AddListener(OnClearButtonClicked);

        if (quitButton != null)
            quitButton.onClick.AddListener(OnQuitButtonClicked);
    }

    private void OnDisable()
    {
        // Always unsubscribe to avoid ghost callbacks after the object is disabled.
        Application.logMessageReceived -= HandleLogReceived;

        if (clearButton != null)
            clearButton.onClick.RemoveListener(OnClearButtonClicked);

        if (quitButton != null)
            quitButton.onClick.RemoveListener(OnQuitButtonClicked);
    }

    // ──────────────────────────────────────────────────────────
    // Log Receiver
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Called by Unity for every Debug.Log / LogWarning / LogError, etc.
    /// Appends a new coloured line to the single TextMeshProUGUI — no instantiation.
    /// </summary>
    private void HandleLogReceived(string message, string stackTrace, LogType logType)
    {
        if (logText == null) return;

        // Trim oldest lines when the cap is reached.
        if (m_Lines.Count >= maxLines)
            m_Lines.RemoveAt(0);

        // Build the formatted line and add it.
        string colour = k_LogColour.TryGetValue(logType, out string hex) ? hex : "#FFFFFF";
        string prefix = GetLogPrefix(logType);
        m_Lines.Add($"<color={colour}>{prefix} {message}</color>");

        // Rebuild the full display string from the line list.
        RefreshText();

        // Scroll to the bottom so the latest line is always visible.
        // LayoutRebuilder is used instead of Canvas.ForceUpdateCanvases() because we
        // need the ScrollRect's content to recalculate its height after the TMP resize.
        if (scrollRect != null)
        {
            LayoutRebuilder.ForceRebuildLayoutImmediate(scrollRect.content);
            scrollRect.verticalNormalizedPosition = 0f;
        }
    }

    // ──────────────────────────────────────────────────────────
    // Button Handlers
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Clears all log lines from the list and the TextMeshProUGUI.
    /// Called by the Clear Button's OnClick event (wired in OnEnable).
    /// </summary>
    public void OnClearButtonClicked()
    {
        m_Lines.Clear();
        if (logText != null)
            logText.text = string.Empty;
    }

    /// <summary>
    /// Hides the config canvas and restores the main canvas.
    /// Called by the Quit Button's OnClick event (wired in OnEnable).
    /// </summary>
    public void OnQuitButtonClicked()
    {
        if (configCanvas != null) configCanvas.SetActive(false);
        if (mainCanvas != null)   mainCanvas.SetActive(true);
    }

    // ──────────────────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────────────────

    /// <summary>
    /// Rebuilds logText.text from the current line list using a StringBuilder
    /// to avoid repeated string concatenation allocations.
    /// </summary>
    private void RefreshText()
    {
        m_Builder.Clear();
        for (int i = 0; i < m_Lines.Count; i++)
            m_Builder.AppendLine(m_Lines[i]);

        logText.text = m_Builder.ToString();

        // Force TMP to immediately recalculate its mesh and preferred dimensions.
        // Without this, preferredHeight still reflects the old text until the next frame.
        logText.ForceMeshUpdate();

        // Resize the TMP RectTransform to exactly fit all the text.
        // This gives the ScrollRect's Content an accurate height to scroll within.
        logText.rectTransform.SetSizeWithCurrentAnchors(
            RectTransform.Axis.Vertical, logText.preferredHeight);
    }

    private static string GetLogPrefix(LogType logType)
    {
        return logType switch
        {
            LogType.Warning   => "[WARN]",
            LogType.Error     => "[ERROR]",
            LogType.Assert    => "[ASSERT]",
            LogType.Exception => "[EXCEPTION]",
            _                 => "[LOG]",
        };
    }
}
