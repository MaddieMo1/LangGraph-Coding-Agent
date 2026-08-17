// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：UnityWebRequestAwaiter.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：扩展 UnityWebRequestAsyncOperation，支持以 Task 形式异步等待网络请求完成，便于使用 async/await 模式。
// ─────────────────────────────────────────────────────────────────────────────

// VoiceSystem/Runtime/UnityWebRequestAwaiter.cs
using System.Threading.Tasks;
using UnityEngine.Networking;

public static class UnityWebRequestAwaiter
{
    /// <summary>
    /// 将 UnityWebRequestAsyncOperation 转换为 Task，用于支持 async/await
    /// </summary>
    /// <param name="_Operation">异步操作对象</param>
    /// <returns>异步任务，完成时返回原始请求对象</returns>
    public static Task<UnityWebRequest> AsTask(this UnityWebRequestAsyncOperation _Operation)
    {
        var _Tcs = new TaskCompletionSource<UnityWebRequest>();

        _Operation.completed += _ =>
        {
            _Tcs.SetResult(_Operation.webRequest);
        };

        return _Tcs.Task;
    }
}
