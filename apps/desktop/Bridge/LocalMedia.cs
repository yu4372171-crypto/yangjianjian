using System;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;

namespace Aive.UI2.Bridge;

public sealed class LocalMedia
{
	private sealed class BoundedStream(FileStream inner, long remaining) : Stream()
	{
		public override bool CanRead => true;

		public override bool CanSeek => false;

		public override bool CanWrite => false;

		public override long Length => inner.Length;

		public override long Position
		{
			get
			{
				return inner.Position;
			}
			set
			{
				throw new NotSupportedException();
			}
		}

		public override int Read(byte[] buffer, int offset, int count)
		{
			int read = inner.Read(buffer, offset, (int)Math.Min(count, remaining));
			remaining -= read;
			return read;
		}

		protected override void Dispose(bool disposing)
		{
			if (disposing)
			{
				inner.Dispose();
			}
			base.Dispose(disposing);
		}

		public override void Flush()
		{
		}

		public override long Seek(long offset, SeekOrigin origin)
		{
			throw new NotSupportedException();
		}

		public override void SetLength(long value)
		{
			throw new NotSupportedException();
		}

		public override void Write(byte[] buffer, int offset, int count)
		{
			throw new NotSupportedException();
		}
	}

	private readonly ConcurrentDictionary<string, string> paths = new ConcurrentDictionary<string, string>(StringComparer.OrdinalIgnoreCase);

	private readonly ConcurrentDictionary<string, string> tokens = new ConcurrentDictionary<string, string>();

	public void Register(JsonElement value)
	{
		if (value.ValueKind == JsonValueKind.Object)
		{
			foreach (JsonProperty property in value.EnumerateObject())
			{
				bool flag = property.Value.ValueKind == JsonValueKind.String;
				if (flag)
				{
					bool flag2 = property.Name.EndsWith("path");
					if (!flag2)
					{
						string name = property.Name;
						bool flag3 = ((name == "path" || name == "source_file") ? true : false);
						flag2 = flag3;
					}
					flag = flag2;
				}
				if (flag)
				{
					string path = property.Value.GetString();
					if (!string.IsNullOrEmpty(path) && Path.IsPathFullyQualified(path) && File.Exists(path))
					{
						Allow(path);
					}
				}
				else
				{
					Register(property.Value);
				}
			}
			return;
		}
		if (value.ValueKind != JsonValueKind.Array)
		{
			return;
		}
		foreach (JsonElement item in value.EnumerateArray())
		{
			Register(item);
		}
	}

	public void Allow(string path)
	{
		string full = Path.GetFullPath(path);
		paths.GetOrAdd(full, delegate(string p)
		{
			string text = Guid.NewGuid().ToString("N");
			tokens[text] = p;
			return text;
		});
	}

	public bool IsAllowed(string path)
	{
		return paths.ContainsKey(Path.GetFullPath(path));
	}

	public string Url(string path)
	{
		string full = Path.GetFullPath(path);
		if (!paths.TryGetValue(full, out string token))
		{
			throw new UnauthorizedAccessException("该文件尚未由项目或文件选择器授权");
		}
		return "https://media.aive.local/" + token + "/" + Uri.EscapeDataString(Path.GetFileName(full));
	}

	public void Respond(CoreWebView2 sender, CoreWebView2WebResourceRequestedEventArgs args)
	{
		try
		{
			string token = new Uri(args.Request.Uri).AbsolutePath.Split('/').ElementAtOrDefault(1) ?? "";
			if (!tokens.TryGetValue(token, out string path) || !File.Exists(path))
			{
				args.Response = sender.Environment.CreateWebResourceResponse(null, 404, "Not Found", "");
				return;
			}
			FileStream file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
			long length = file.Length;
			long start = 0L;
			long end = length - 1;
			string range = (args.Request.Headers.Contains("Range") ? args.Request.Headers.GetHeader("Range") : "");
			bool partial = range.StartsWith("bytes=");
			string text;
			if (partial)
			{
				text = range;
				string[] parts = text.Substring(6, text.Length - 6).Split('-');
				if (parts[0].Length == 0)
				{
					long suffix = long.Parse(parts[1]);
					start = Math.Max(0L, length - suffix);
				}
				else
				{
					start = long.Parse(parts[0]);
					if (parts.Length > 1 && parts[1].Length > 0)
					{
						end = Math.Min(end, long.Parse(parts[1]));
					}
				}
			}
			if (start < 0 || start >= length || end < start)
			{
				file.Dispose();
				args.Response = sender.Environment.CreateWebResourceResponse(null, 416, "Range Not Satisfiable", $"Content-Range: bytes */{length}\r\n");
				return;
			}
			file.Seek(start, SeekOrigin.Begin);
			string ext = Path.GetExtension(path).ToLowerInvariant();
			if (ext != null)
			{
				int length2 = ext.Length;
				if (length2 != 4)
				{
					if (length2 == 5)
					{
						char c = ext[4];
						if (c != 'g')
						{
							if (c != 'm')
							{
								if (c != 'p' || !(ext == ".webp"))
								{
									goto IL_0384;
								}
								text = "image/webp";
							}
							else
							{
								if (!(ext == ".webm"))
								{
									goto IL_0384;
								}
								text = "video/webm";
							}
							goto IL_038b;
						}
						if (ext == ".jpeg")
						{
							goto IL_0360;
						}
					}
				}
				else
				{
					char c = ext[1];
					if ((uint)c > 106u)
					{
						if (c != 'm')
						{
							if (c != 'p')
							{
								if (c != 'w' || !(ext == ".wav"))
								{
									goto IL_0384;
								}
								text = "audio/wav";
							}
							else
							{
								if (!(ext == ".png"))
								{
									goto IL_0384;
								}
								text = "image/png";
							}
						}
						else
						{
							switch (ext)
							{
							case ".mp4":
								break;
							case ".mov":
								goto IL_033c;
							case ".mp3":
								goto IL_0345;
							default:
								goto IL_0384;
							}
							text = "video/mp4";
						}
						goto IL_038b;
					}
					if (c != 'b')
					{
						if (c != 'g')
						{
							if (c == 'j' && ext == ".jpg")
							{
								goto IL_0360;
							}
						}
						else if (ext == ".gif")
						{
							text = "image/gif";
							goto IL_038b;
						}
					}
					else if (ext == ".bmp")
					{
						text = "image/bmp";
						goto IL_038b;
					}
				}
			}
			goto IL_0384;
			IL_0360:
			text = "image/jpeg";
			goto IL_038b;
			IL_0345:
			text = "audio/mpeg";
			goto IL_038b;
			IL_038b:
			string type = text;
			string headers = $"Content-Type: {type}\r\nContent-Length: {end - start + 1}\r\nAccept-Ranges: bytes\r\nAccess-Control-Allow-Origin: https://app.aive.local\r\n";
			if (partial)
			{
				headers += $"Content-Range: bytes {start}-{end}/{length}\r\n";
			}
			args.Response = sender.Environment.CreateWebResourceResponse(new BoundedStream(file, end - start + 1), partial ? 206 : 200, partial ? "Partial Content" : "OK", headers);
			return;
			IL_033c:
			text = "video/quicktime";
			goto IL_038b;
			IL_0384:
			text = "application/octet-stream";
			goto IL_038b;
		}
		catch (Exception ex)
		{
			HostLog.Write("Media preview: " + ex.Message);
			args.Response = sender.Environment.CreateWebResourceResponse(null, 500, "Preview error", "");
		}
	}
}
