import contextlib
import io
import random
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import discord

from cogs import config as cfg

POTD_RANGE = "POTD!A2:S"
CURATOR_RANGE = "Curators!A3:E"


def is_pc(ctx):
    if ctx.guild is None:
        return False
    return cfg.Config.config["problem_curator_role"] in [x.id for x in ctx.author.roles]


async def dm_or_channel(
    user: discord.User, channel: discord.abc.Messageable, content="", *args, **kargs
):
    try:
        if user is not None and not user.bot:
            await user.send(*args, content=content, **kargs)
    except Exception:
        await channel.send(*args, content=user.mention + "\n" + content, **kargs)


def curator_id(curators, value):
    value = str(value)
    if not value:
        return None
    for i in curators:
        for j in range(min(len(i), 4)):
            if value == str(i[j]):
                return i[0]
    return None


def generate_source(potd_row, display=True, caller_id=0):
    # Figure out whose potd it is
    curators = (
        cfg.Config.service.spreadsheets()
        .values()
        .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=CURATOR_RANGE)
        .execute()
        .get("values", [])
    )
    potd_curator_id = curator_id(curators, potd_row[3])
    curator = "Unknown Curator" if potd_curator_id is None else f"<@!{potd_curator_id}>"
    # TODO: investigate this
    difficulty_length = len(potd_row[5]) + len(potd_row[6])  # noqa: F841
    padding = " " * (max(35 - len(potd_row[4]), 1))
    has_hint = "✅" if (potd_row[9].strip() != "") else "❌"
    has_answer = "✅" if (potd_row[12].strip() != "") else "❌"
    has_solution = (
        "✅" if (potd_row[14].strip() != "" or potd_row[15].strip() != "") else "❌"
    )

    source = discord.Embed()
    source.add_field(name="Curator", value=curator)

    if display:
        source.add_field(name="Source", value=f"||`{potd_row[4]}{padding}`||")
        source.add_field(name="Difficulty", value=f"||`{str(potd_row[6]).ljust(5)}`||")
        source.add_field(name="Genre", value=f"||`{str(potd_row[5]).ljust(5)}`||")
    else:
        source.add_field(name="Source", value="(To be revealed)")
        source.add_field(name="Difficulty", value="(To be revealed)")
        source.add_field(name="Genre", value="(To be revealed)")

    source.add_field(name="Hint", value=has_hint)
    source.add_field(name="Answer", value=has_answer)
    source.add_field(name="Solution", value=has_solution)

    # Community Rating footer
    cursor = cfg.db.cursor()

    cursor.execute(
        f"""SELECT blacklisted_user_id
    FROM potd_rater_blacklist
    WHERE discord_user_id = {caller_id}
    LIMIT 1000000;"""
    )
    blacklisted_users = list(map(lambda x: x[0], cursor.fetchall()))
    blacklisted_users_string = "('" + "','".join(map(str, blacklisted_users)) + "')"

    cursor.execute(
        f"SELECT * FROM ratings WHERE prob = {potd_row[0]} "
        f"AND userid not in {blacklisted_users_string}"
    )
    result = cursor.fetchall()

    community_rating = ""
    if len(result) > 0:
        community_rating += f"There are {len(result)} community difficulty ratings. "
        if display:
            with contextlib.suppress(Exception):
                underrate_count = sum(row[3] < int(potd_row[6]) for row in result)
                if underrate_count > 0:
                    community_rating += (
                        f"{underrate_count} rated lower than current rating. "
                    )
                overrate_count = sum(row[3] > int(potd_row[6]) for row in result)
                if overrate_count > 0:
                    community_rating += (
                        f"{overrate_count} rated higher than current rating. "
                    )
        community_rating += "\n"

    # Final footer
    text = (
        f"{community_rating}Use -rating {potd_row[0]} to check the community "
        f"difficulty rating of this problem or -rate {potd_row[0]} rating to rate "
        "it yourself. React with a 👍 if you liked the problem. "
    )
    source.set_footer(text=text)

    return source


async def edit_source(bot, potd):
    sheet = get_potd_sheet()
    potd_row = get_potd_row(potd, sheet)
    with contextlib.suppress(Exception):
        potd_source = (
            generate_source(potd_row, True)
            if datetime.now() - timedelta(hours=10) - timedelta(days=1)
            > datetime.strptime(
                potd_row[cfg.Config.config["potd_sheet_date_col"]], "%d %b %Y"
            )
            else generate_source(potd_row, False)
        )
        potd_source_msg_id = potd_row[cfg.Config.config["potd_sheet_message_id_col"]]
        potd_source_msg = await bot.get_channel(
            cfg.Config.config["potd_channel"]
        ).fetch_message(potd_source_msg_id)
        await potd_source_msg.edit(embed=potd_source)


async def fetch(ctx, number: int, flag: str = ""):
    sheet = get_potd_sheet()
    potd_row = get_potd_row(number, sheet)

    if potd_row is None:
        await ctx.send(f"There is no potd for day {number}. ")
        return
    else:
        # Create the message to send
        try:
            # if there is image link, just send it out
            image_link = check_for_image_link(potd_row)
            if image_link and "t" not in flag:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_link) as resp:
                        if resp.status != 200:
                            return await ctx.send("Could not download file...")
                        data = io.BytesIO(await resp.read())
                        if "s" not in flag:
                            await ctx.send(file=discord.File(data, f"potd{number}.png"))
                        else:
                            await ctx.send(
                                file=discord.File(data, f"SPOILER_potd{number}.png")
                            )
            # if no image link, send tex
            else:
                if "s" not in flag:
                    output = (
                        "<@"
                        + str(cfg.Config.config["paradox_id"])
                        + ">\n"
                        + texify_potd(potd_row)
                    )
                else:
                    output = (
                        "<@"
                        + str(cfg.Config.config["paradox_id"])
                        + ">texsp\n||"
                        + texify_potd(potd_row)
                        + "||"
                    )
                await ctx.send(output, delete_after=5)
        except IndexError:
            await ctx.send(f"There is no potd for day {number}. ")
            return


def check_for_image_link(potd_row) -> Optional[str]:
    if len(potd_row) >= 19 and potd_row[
        cfg.Config.config["potd_sheet_image_link_col"]
    ] not in [None, ""]:
        return potd_row[cfg.Config.config["potd_sheet_image_link_col"]]
    else:
        return None


def texify_potd(potd_row) -> str:
    return (
        "```tex\n\\textbf{Day "
        + str(potd_row[cfg.Config.config["potd_sheet_id_col"]])
        + "} --- "
        + str(potd_row[cfg.Config.config["potd_sheet_day_col"]])
        + " "
        + str(potd_row[cfg.Config.config["potd_sheet_date_col"]])
        + "\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}"
        + str(potd_row[cfg.Config.config["potd_sheet_statement_col"]])
        + "```"
    )


def pick_potd(
    diff_lower_bound_filter,
    diff_upper_bound_filter,
    genre_filter,
    potds,
    already_picked,
    ctx,
    search_unsolved: bool,
    tag_filter="",
):
    solved_potd = []
    if search_unsolved:
        get_solved_potd = get_potd_solved(ctx)
        get_read_potd = get_potd_read(ctx)
        solved_potd = get_solved_potd + get_read_potd

    def match_genre(x, genre_filter):
        if len(genre_filter) == 0:
            return True
        for genre in genre_filter:
            if len(
                set(x[cfg.Config.config["potd_sheet_genre_col"]]).intersection(genre)
            ) == len(genre):
                return True
        return False

    def match_tag(x, tag_filter):
        if tag_filter == "":
            return True
        tags = [
            y.strip() for y in x[cfg.Config.config["potd_sheet_tags_col"]].split(",")
        ]
        return tag_filter in tags

    today = datetime.strptime(datetime.now().strftime("%d %b %Y"), "%d %b %Y")

    # filter by genre and difficulty
    if type(diff_upper_bound_filter) is int:
        filtered_potds = [
            x
            for x in potds
            if len(x)
            > max(
                cfg.Config.config["potd_sheet_difficulty_col"],
                cfg.Config.config["potd_sheet_genre_col"],
            )
            and x[cfg.Config.config["potd_sheet_difficulty_col"]].isnumeric()
            and int(x[cfg.Config.config["potd_sheet_difficulty_col"]])
            >= diff_lower_bound_filter
            and int(x[cfg.Config.config["potd_sheet_difficulty_col"]])
            <= diff_upper_bound_filter
            and match_genre(x, genre_filter)
            and match_tag(x, tag_filter)
            and datetime.strptime(
                x[cfg.Config.config["potd_sheet_date_col"]], "%d %b %Y"
            )
            < today
        ]
    else:  # if diff bound is "T"
        filtered_potds = [
            x
            for x in potds
            if len(x)
            > max(
                cfg.Config.config["potd_sheet_difficulty_col"],
                cfg.Config.config["potd_sheet_genre_col"],
            )
            and (
                (
                    x[cfg.Config.config["potd_sheet_difficulty_col"]].isnumeric()
                    and int(x[cfg.Config.config["potd_sheet_difficulty_col"]])
                    >= diff_lower_bound_filter
                )
                or not x[cfg.Config.config["potd_sheet_difficulty_col"]].isnumeric()
            )
            and match_genre(x, genre_filter)
            and match_tag(x, tag_filter)
            and datetime.strptime(
                x[cfg.Config.config["potd_sheet_date_col"]], "%d %b %Y"
            )
            < today
        ]

    # pick a POTD
    if filtered_potds:
        filtered_potds_id = list(
            map(
                lambda x: int(x[cfg.Config.config["potd_sheet_id_col"]]),
                filtered_potds,
            )
        )
        unsolved_potds_id = [
            x
            for x in filtered_potds_id
            if x not in solved_potd
            if x not in already_picked
        ]
        if unsolved_potds_id:
            picked_potd = int(random.choice(unsolved_potds_id))
        else:
            not_repeated_potds_id = [
                x for x in filtered_potds_id if x not in already_picked
            ]
            if not_repeated_potds_id:
                picked_potd = int(random.choice(not_repeated_potds_id))
            else:
                picked_potd = int(random.choice(filtered_potds_id))
        return picked_potd
    else:
        return None


def get_potd_statement(number: int, potds):
    current_potd = int(
        potds[0][0]
    )  # this will be the top left cell which indicates the latest added potd

    if number > current_potd:
        return None

    potd_row = potds[current_potd - number]  # this gets the row requested

    # Create the tex
    try:
        return potd_row[cfg.Config.config["potd_sheet_statement_col"]]
    except IndexError:
        return None


def get_potd_solved(ctx):
    cursor = cfg.db.cursor()
    cursor.execute(
        "SELECT discord_user_id, potd_id, create_date FROM potd_solves "
        f"WHERE discord_user_id = {ctx.author.id} "
        "ORDER BY potd_id DESC"
    )
    return [x[1] for x in cursor.fetchall()]


def get_potd_read(ctx):
    cursor = cfg.db.cursor()
    cursor.execute(
        "SELECT discord_user_id, potd_id, create_date FROM potd_read "
        f"WHERE discord_user_id = {ctx.author.id} "
        "ORDER BY potd_id DESC"
    )
    return [x[1] for x in cursor.fetchall()]


def get_potd_todo(ctx):
    cursor = cfg.db.cursor()
    cursor.execute(
        "SELECT discord_user_id, potd_id, create_date FROM potd_todo "
        f"WHERE discord_user_id = {ctx.author.id} "
        "ORDER BY potd_id DESC"
    )
    return [x[1] for x in cursor.fetchall()]


def get_potd_rated(ctx):
    cursor = cfg.db.cursor()
    cursor.execute(f"SELECT * FROM ratings WHERE userid = {ctx.author.id}")
    return [x[1] for x in cursor.fetchall()]


def get_potd_sheet():
    return (
        cfg.Config.service.spreadsheets()
        .values()
        .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
        .execute()
    )


def get_potd_row(number, sheet):
    values = sheet.get("values", [])
    current_potd = int(
        values[0][0]
    )  # this will be the top left cell which indicates the latest added potd

    if number > current_potd or number < 1:
        return None

    try:
        return values[current_potd - number]
    except IndexError:
        return None
