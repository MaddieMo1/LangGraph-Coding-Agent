using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using System;

[Serializable]
public class AsrResultItem
{
    public string key;
    public string text;
    public string raw_text;
    public string clean_text;
}

[Serializable]
public class AsrResponse
{
    public List<AsrResultItem> result;
}

public class FastApiAsrClient : MonoBehaviour
{
    [Header("API 设置")]
    public string _ApiUrl = "http://127.0.0.1:8000/api/v1/asr";

    /// <summary>
    /// 上传一段内存中的音频数据进行识别
    /// </summary>
    /// <param name="_AudioData">WAV或MP3字节流</param>
    /// <param name="_FileName">文件名（含扩展名），后端用来判断格式</param>
    public IEnumerator UploadAndRecognize(byte[] _AudioData, string _FileName)
    {
        // 构造 multipart/_Form-data
        var _Form = new List<IMultipartFormSection>
        {
            new MultipartFormFileSection("files", _AudioData, _FileName,
                _FileName.EndsWith(".mp3", StringComparison.OrdinalIgnoreCase)
                  ? "audio/mpeg" : "audio/wav"),
            new MultipartFormDataSection("keys", _FileName)
        };

        using var _UnityWebRequest = UnityWebRequest.Post(_ApiUrl, _Form);
        _UnityWebRequest.timeout = 30;
        yield return _UnityWebRequest.SendWebRequest();

        if (_UnityWebRequest.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError($"[ASR] 接口调用失败: {_UnityWebRequest.error}");
            yield break;
        }

        // 解析返回 JSON
        string json = _UnityWebRequest.downloadHandler.text;
        Debug.Log($"[ASR] 原始返回:\n{json}");

        AsrResponse _Resp = null;
        try
        {
            _Resp = JsonUtility.FromJson<AsrResponse>(json);
        }
        catch (Exception e)
        {
            Debug.LogError($"[ASR] JSON 解析失败: {e.Message}");
            yield break;
        }

        // 输出识别结果
        if (_Resp.result != null && _Resp.result.Count > 0)
        {
            foreach (var _Item in _Resp.result)
            {
                Debug.Log($"[ASR] Key: {_Item.key}\n" +
                          $"Text: {_Item.text}\n" +
                          $"Clean: {_Item.clean_text}\n");
            }
        }
        else
        {
            Debug.LogWarning("[ASR] 返回 result 为空");
        }
    }
}