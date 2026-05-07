#!/usr/bin/env python3
"""Quick Matrix connectivity test — sends a DM to a target user.

Usage:
    python scripts/test_matrix.py [target_user_id]

Defaults to @martin:matrix.bitforged.com.
"""
import asyncio
import sys
import time

import httpx

HOMESERVER = "https://matrix.bitforged.com"
ACCESS_TOKEN = "t0n8ccYb4mTt6CWBTcNlSl7xpb0IqhPs"
SENDER = "@portfolio-alert:matrix.bitforged.com"
DEFAULT_TARGET = "@martin:matrix.bitforged.com"


async def get_or_create_dm_room(client: httpx.AsyncClient, target: str) -> str:
    """Return an existing DM room with *target* or create one."""
    # Check account_data for existing DM rooms
    resp = await client.get(f"{HOMESERVER}/_matrix/client/v3/user/{SENDER}/account_data/m.direct")
    if resp.status_code == 200:
        dm_map: dict = resp.json()
        rooms = dm_map.get(target, [])
        if rooms:
            room_id = rooms[0]
            print(f"  Found existing DM room: {room_id}")
            return room_id

    # Create a new DM room
    print(f"  No existing DM room found — creating one...")
    resp = await client.post(
        f"{HOMESERVER}/_matrix/client/v3/createRoom",
        json={
            "is_direct": True,
            "invite": [target],
            "preset": "trusted_private_chat",
        },
    )
    resp.raise_for_status()
    room_id = resp.json()["room_id"]
    print(f"  Created room: {room_id}")

    # Store in account_data so future calls reuse it
    dm_map = {} if resp.status_code != 200 else resp.json()
    existing = dm_map.get(target, [])
    existing.append(room_id)
    await client.put(
        f"{HOMESERVER}/_matrix/client/v3/user/{SENDER}/account_data/m.direct",
        json={**dm_map, target: existing},
    )
    return room_id


async def send_message(client: httpx.AsyncClient, room_id: str, body: str) -> None:
    txn_id = f"test-{int(time.time() * 1000)}"
    url = f"{HOMESERVER}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
    resp = await client.put(url, json={"msgtype": "m.text", "body": body})
    resp.raise_for_status()
    print(f"  Sent — event_id: {resp.json().get('event_id')}")
    print(resp.json())


async def main(target: str) -> None:
    print(f"Matrix connectivity test")
    print(f"  Homeserver : {HOMESERVER}")
    print(f"  Sender     : {SENDER}")
    print(f"  Target     : {target}")
    print()

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        timeout=15.0,
    ) as client:
        # Verify credentials
        resp = await client.get(f"{HOMESERVER}/_matrix/client/v3/account/whoami")
        if resp.status_code != 200:
            print(f"ERROR: whoami failed ({resp.status_code}): {resp.text[:200]}")
            sys.exit(1)
        print(f"Authenticated as: {resp.json().get('user_id')}")

        room_id = await get_or_create_dm_room(client, target)
        message = f"[Nexus Portfolio Monitor] Test message — Matrix delivery is working."
        await send_message(client, room_id, message)
        print()
        print("Done.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    asyncio.run(main(target))
