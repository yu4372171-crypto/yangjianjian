using System;
using System.Collections.Generic;

namespace Aive.UI2.Announcements;

public sealed record AnnouncementSnapshot(IReadOnlyList<Announcement> Items, DateTimeOffset? LastFetchTime, bool FromCache);
