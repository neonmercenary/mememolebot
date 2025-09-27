from datetime import datetime, timedelta, timezone
import peewee as pw


db = pw.SqliteDatabase('memebot.db')


class BaseModel(pw.Model):
    class Meta:
        database = db


class User(BaseModel):
    """Telegram user."""
    id          = pw.BigIntegerField(primary_key=True)          # telegram id
    name        = pw.CharField(null=True)
    risk_pct    = pw.FloatField(default=0.50)                   # 0-1
    cashout_pct = pw.FloatField(default=0.70)                   # stop-loss from entry (0-1)
    created_at  = pw.DateTimeField(default=datetime.now(timezone.utc))


class WatchList(BaseModel):
    """Previously blown-up meme addresses to flag on new launches."""
    address     = pw.CharField(unique=True)                     # token mint
    reason      = pw.CharField(null=True)                       # optional note
    added_at    = pw.DateTimeField(default=datetime.now(timezone.utc))


class Transaction(BaseModel):
    """Single buy or sell row."""
    SIDE_CHOICES = (("BUY", "Buy"), ("SELL", "Sell"))
    user        = pw.ForeignKeyField(User, backref="transactions")
    side        = pw.CharField(choices=SIDE_CHOICES, max_length=4)
    amount_sol  = pw.FloatField()                               # SOL size
    amount_token= pw.FloatField()                               # token size
    ticker      = pw.CharField()
    mint        = pw.CharField()                                # token mint address
    tx_hash     = pw.CharField(unique=True)
    price_sol   = pw.FloatField()                               # price per token in SOL
    created_at  = pw.DateTimeField(default=datetime.now(timezone.utc))


# create tables if they don’t exist
db.create_tables([User, WatchList, Transaction])