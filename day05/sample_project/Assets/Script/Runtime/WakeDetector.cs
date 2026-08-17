// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：WakeDetector.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：基于 Unity KeywordRecognizer 实现关键词识别，触发唤醒或声纹注册、退出等事件。
// ─────────────────────────────────────────────────────────────────────────────

// VoiceSystem/Runtime/WakeDetector.cs
using UnityEngine;
using UnityEngine.Windows.Speech;
using System.Linq;


[AddComponentMenu("VoiceSystem/Runtime/Wake Detector")]
public sealed class WakeDetector : MonoBehaviour
{
    [Header("唤醒关键词（大小写忽略）")]
    [SerializeField] string[] _WakeWords = { "你好 西奥多尔", "西奥多尔", "Theodore", "注册" };

    KeywordRecognizer _Recognizer;

    [SerializeField] string _StopWord = "停止";

    /// <summary>
    /// 初始化唤醒词识别器并开始监听
    /// </summary>
    void Start()
    {
        _WakeWords = _WakeWords.Concat(new[] { _StopWord }).ToArray();
        _Recognizer = new KeywordRecognizer(_WakeWords, ConfidenceLevel.Medium);
        _Recognizer.OnPhraseRecognized += OnPhrase;
        _Recognizer.Start();
        Debug.Log("[WakeDetector] 关键词监听启动");
    }

    /// <summary>
    /// 释放识别器资源
    /// </summary>
    void OnDestroy()
    {
        if (_Recognizer != null)
        {
            _Recognizer.OnPhraseRecognized -= OnPhrase;
            _Recognizer.Dispose();
        }
    }

    /// <summary>
    /// 回调处理：检测到关键词触发相应操作
    /// </summary>
    /// <param name="_Args">识别结果</param>
    void OnPhrase(PhraseRecognizedEventArgs _Args)
    {
        //Debug.Log($"[WakeDetector] 用户说了：{_Args.text}");

        if (_WakeWords.Contains(_Args.text))
        {
            if (_Args.text == "注册")
            {
                Debug.Log($"[WakeDetector] 注册词触发: {_Args.text}");

                var _Svc = FindObjectOfType<SpeakerSvcProxy>();
                if (_Svc != null)
                {
                    _Svc.EnterRegisterMode();
                    Debug.Log("[WakeDetector] 已进入注册模式");
                }

                // 同时唤醒进入录音
                EventBus.RaiseWake();
            }
            else if (_Args.text == _StopWord)
            {
                Debug.Log($"[WakeDetector] 退出词触发: {_Args.text}");
                EventBus.RaiseExit();
            }
            else
            {
                Debug.Log($"[WakeDetector] 唤醒词触发: {_Args.text}");
                EventBus.RaiseWake();
            }
        }
    }
}