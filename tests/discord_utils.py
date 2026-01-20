

guilds = {}

class StubRole:
    def __init__(self, role_id, precedence):
        self.id = role_id
        self.precedence = precedence

    def __gt__(self, other):
        return self.precedence > other.precedence

    def __lt__(self, other):
        return self.precedence < other.precedence

    def __eq__(self, other):
        return self.precedence == other.precedence
        


class Channel:
    def __init__(self, channel_id):
        self.id = channel_id

    async def send(self, *args, **kwargs):
        pass

        


class StubMember:
    def __init__(self, user_id, roles, guild=None):
        self.id = user_id
        self.roles = roles
        self.guild = guild
        self.mention = f'<@{user_id}>'
        self.dm_channel = None
        messages = None

    async def create_dm(self):
        return Channel(self.id+10)

        



class StubGuild:
    def __init__(self, guild_id, members, roles):
        self.id = guild_id
        self.members = members
        self.roles = roles

    async def fetch_member(self, user_id):
        m = [member for member in self.members if member.id == user_id]
        if m:
            return m[0]
        return None



class StubBot:
    def __init__(self):
        pass

    async def fetch_guild(self, guild_id):
        g = guilds.get(guild_id)
        if g is not None:
            return g
        g = StubGuild(guild_id, [], [])
        guilds[guild_id] = g
        return g

    async def fetch_user(self, user_id):
        return StubMember(user_id, [])



