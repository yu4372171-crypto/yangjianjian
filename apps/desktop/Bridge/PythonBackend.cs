using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Aive.UI2.Bridge;

public sealed class PythonBackend : IAsyncDisposable
{
	private readonly ConcurrentDictionary<string, TaskCompletionSource<JsonElement>> pending = new ConcurrentDictionary<string, TaskCompletionSource<JsonElement>>();

	private readonly SemaphoreSlim writer = new SemaphoreSlim(1, 1);

	private Process? process;

	private Task? readerTask;

	private bool stopping;

	public static string? SourceRoot
	{
		get
		{
			for (DirectoryInfo? dir = new(AppContext.BaseDirectory); dir != null; dir = dir.Parent)
			{
				if (File.Exists(Path.Combine(dir.FullName, "backend", "run_ui2_backend.py")))
				{
					return dir.FullName;
				}
			}
			return null;
		}
	}

	public event Action<JsonElement>? EventReceived;

	public event Action<string>? Failed;

	public void Start()
	{
		string packaged = Path.Combine(AppContext.BaseDirectory, "Backend", "aive-business.exe");
		ProcessStartInfo info = new ProcessStartInfo
		{
			UseShellExecute = false,
			RedirectStandardInput = true,
			RedirectStandardOutput = true,
			RedirectStandardError = true,
			CreateNoWindow = true,
			StandardOutputEncoding = Encoding.UTF8,
			StandardErrorEncoding = Encoding.UTF8,
			StandardInputEncoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)
		};
		if (File.Exists(packaged))
		{
			info.FileName = packaged;
			info.WorkingDirectory = Path.GetDirectoryName(packaged);
		}
		else
		{
			string root = SourceRoot ?? throw new FileNotFoundException("未找到业务运行时。请使用完整发布目录，或在源码目录构建。");
			string configured = Environment.GetEnvironmentVariable("AIVE_PYTHON");
			string[] candidates = new string[3]
			{
				configured,
				Path.Combine(root, ".venv", "Scripts", "python.exe"),
				Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".workbuddy", "binaries", "python", "envs", "default", "Scripts", "python.exe")
			};
			info.FileName = candidates.FirstOrDefault((string p) => p != null && File.Exists(p)) ?? throw new FileNotFoundException("找不到 Python 环境，请运行 UI2/build.ps1 或指定 AIVE_PYTHON。");
			info.ArgumentList.Add("-u");
			info.ArgumentList.Add(Path.Combine(root, "backend", "run_ui2_backend.py"));
			info.WorkingDirectory = Path.Combine(root, "backend");
		}
		info.Environment["PYTHONUTF8"] = "1";
		process = new Process
		{
			StartInfo = info,
			EnableRaisingEvents = true
		};
		process.ErrorDataReceived += delegate(object _, DataReceivedEventArgs e)
		{
			if (e.Data != null)
			{
				HostLog.Write(e.Data);
			}
		};
		process.Start();
		process.BeginErrorReadLine();
		readerTask = ReadAsync();
	}

	private async Task ReadAsync()
	{
		try
		{
			string line = default(string);
			while (true)
			{
				bool flag = process != null;
				if (flag)
				{
					line = await process.StandardOutput.ReadLineAsync();
					flag = line != null;
				}
				if (!flag)
				{
					break;
				}
				JsonElement value;
				JsonElement packet;
				try
				{
					using JsonDocument doc = JsonDocument.Parse(line);
					value = doc.RootElement;
					packet = value.Clone();
				}
				catch (JsonException)
				{
					HostLog.Write("Ignored non-protocol backend output");
					continue;
				}
				if (packet.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String)
				{
					string requestId = id.GetString();
					if (requestId != null && requestId.Length > 0 && pending.TryRemove(requestId, out TaskCompletionSource<JsonElement> reply))
					{
						reply.TrySetResult(packet);
						continue;
					}
				}
				if (packet.TryGetProperty("event", out value))
				{
					this.EventReceived?.Invoke(packet);
				}
				else
				{
					if (!packet.TryGetProperty("error", out var error) || error.ValueKind != JsonValueKind.Object)
					{
						continue;
					}
					JsonElement text;
					string message = (error.TryGetProperty("message", out text) ? text.GetString() : "业务协议异常");
					HostLog.Write("Backend protocol failure: " + message);
					foreach (KeyValuePair<string, TaskCompletionSource<JsonElement>> item in pending)
					{
						if (pending.TryRemove(item.Key, out TaskCompletionSource<JsonElement> unresolved))
						{
							unresolved.TrySetException(new IOException(message));
						}
					}
				}
			}
			if (!stopping)
			{
				throw new IOException("业务进程已退出，请查看运行日志或重新启动。");
			}
		}
		catch (Exception ex2)
		{
			HostLog.Write(ex2.ToString());
			foreach (KeyValuePair<string, TaskCompletionSource<JsonElement>> item2 in pending)
			{
				if (pending.TryRemove(item2.Key, out TaskCompletionSource<JsonElement> reply2))
				{
					reply2.TrySetException(ex2);
				}
			}
			this.Failed?.Invoke(ex2.Message);
		}
	}

	public async Task<JsonElement> InvokeAsync(JsonElement request)
	{
		string id = request.GetProperty("id").GetString();
		TaskCompletionSource<JsonElement> reply = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
		if (!pending.TryAdd(id, reply))
		{
			throw new InvalidOperationException("请求编号重复");
		}
		try
		{
			await writer.WaitAsync();
			try
			{
				if (process == null || process.HasExited)
				{
					throw new IOException("业务进程不可用");
				}
				await process.StandardInput.WriteLineAsync(request.GetRawText());
				await process.StandardInput.FlushAsync();
			}
			finally
			{
				writer.Release();
			}
			return await reply.Task.WaitAsync(TimeSpan.FromMinutes(3.0));
		}
		finally
		{
			pending.TryRemove(id, out TaskCompletionSource<JsonElement> _);
		}
	}

	public async ValueTask DisposeAsync()
	{
		stopping = true;
		if (process != null && !process.HasExited)
		{
			try
			{
				await process.StandardInput.WriteLineAsync("{\"id\":\"shutdown\",\"action\":\"app.shutdown\",\"data\":{}}");
				await process.StandardInput.FlushAsync();
				await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(8.0));
			}
			catch (Exception ex)
			{
				HostLog.Write("Backend shutdown: " + ex.Message);
				if (!process.HasExited)
				{
					process.Kill(entireProcessTree: true);
				}
			}
		}
		if (readerTask != null)
		{
			await readerTask;
		}
		process?.Dispose();
		writer.Dispose();
	}
}
