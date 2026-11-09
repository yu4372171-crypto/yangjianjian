using System;
using System.IO;

namespace Aive.UI2;

public static class HostLog
{
	private static readonly object Gate = new object();

	public static string DataDirectory => Environment.GetEnvironmentVariable("AIVE_DATA_DIR") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".aive");

	public static void Write(string message)
	{
		try
		{
			lock (Gate)
			{
				string text = Path.Combine(DataDirectory, "logs");
				Directory.CreateDirectory(text);
				File.AppendAllText(Path.Combine(text, "ui2-host.log"), $"[{DateTime.Now:O}] {message}\n");
			}
		}
		catch (IOException)
		{
		}
	}
}
