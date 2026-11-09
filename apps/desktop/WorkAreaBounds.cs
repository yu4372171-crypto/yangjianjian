using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace Aive.UI2;

internal static class WorkAreaBounds
{
	private struct Point
	{
		public int X;

		public int Y;
	}

	private struct Rect
	{
		public int Left;

		public int Top;

		public int Right;

		public int Bottom;
	}

	private struct MinMaxInfo
	{
		public Point Reserved;

		public Point MaxSize;

		public Point MaxPosition;

		public Point MinTrackSize;

		public Point MaxTrackSize;
	}

	private struct MonitorInfo
	{
		public int Size;

		public Rect Monitor;

		public Rect Work;

		public uint Flags;
	}

	public static void Attach(Window window)
	{
		HwndSource.FromHwnd(new WindowInteropHelper(window).Handle)?.AddHook(WindowMessage);
	}

	private static nint WindowMessage(nint hwnd, int message, nint wParam, nint lParam, ref bool handled)
	{
		if (message != 36)
		{
			return IntPtr.Zero;
		}
		nint monitor = MonitorFromWindow(hwnd, 2u);
		MonitorInfo info = new MonitorInfo
		{
			Size = Marshal.SizeOf<MonitorInfo>()
		};
		if (!GetMonitorInfo(monitor, ref info))
		{
			return IntPtr.Zero;
		}
		MinMaxInfo bounds = Marshal.PtrToStructure<MinMaxInfo>(lParam);
		bounds.MaxPosition.X = info.Work.Left - info.Monitor.Left;
		bounds.MaxPosition.Y = info.Work.Top - info.Monitor.Top;
		bounds.MaxSize.X = info.Work.Right - info.Work.Left;
		bounds.MaxSize.Y = info.Work.Bottom - info.Work.Top;
		Marshal.StructureToPtr(bounds, lParam, fDeleteOld: false);
		return IntPtr.Zero;
	}

	[DllImport("user32.dll")]
	private static extern nint MonitorFromWindow(nint hwnd, uint flags);

	[DllImport("user32.dll", CharSet = CharSet.Auto)]
	[return: MarshalAs(UnmanagedType.Bool)]
	private static extern bool GetMonitorInfo(nint monitor, ref MonitorInfo info);
}
