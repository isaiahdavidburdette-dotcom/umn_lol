import discord
from discord.ext import commands
import pandas as pd
import os
import requests
from datetime import datetime
import asyncio

# ============================
# HARD-CODED TOKEN
# ============================
TOKEN = "MTQ3MDYzOTU4ODM1ODc1NDQ5OA.GGYd6b.mNGcR521n9L894EmEyU3xfWPBwRXq11Y-UmEj4"  # <-- Put your token here

# ============================
# INTENTS SETUP
# ============================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================
# LOAD CSV DATA
# ============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "CLASS_DATA", "combined_clean_data.csv")

print("Loading CSV data...")
df = pd.read_csv(CSV_PATH, dtype=str, low_memory=False)
print(f"✅ Loaded {len(df):,} rows")

# Convert grade count to integer
df['GRADE_HDCNT'] = pd.to_numeric(df['GRADE_HDCNT'], errors='coerce').fillna(0).astype(int)

print("✅ Data processed")

# ============================
# CACHE FOR PERFORMANCE
# ============================
gpa_cache = {}


def precompute_gpas():
    """Precompute GPAs for all courses at startup"""
    print("Precomputing GPAs for all courses...")

    grade_points = {
        'A+': 4.0, 'A': 4.0, 'A-': 3.67,
        'B+': 3.33, 'B': 3.0, 'B-': 2.67,
        'C+': 2.33, 'C': 2.0, 'C-': 1.67,
        'D+': 1.33, 'D': 1.0, 'F': 0.0
    }

    for course in df['FULL_NAME'].unique():
        course_data = df[df['FULL_NAME'] == course]

        total_points = 0
        total_students = 0
        grade_dist = {}

        for _, row in course_data.iterrows():
            grade = row['CRSE_GRADE_OFF']
            count = int(row['GRADE_HDCNT'])

            if grade not in grade_dist:
                grade_dist[grade] = 0
            grade_dist[grade] += count

            if grade in grade_points:
                total_points += grade_points[grade] * count
                total_students += count

        avg_gpa = total_points / total_students if total_students > 0 else 0
        gpa_cache[course] = (avg_gpa, grade_dist)

    print(f"✅ Precomputed GPAs for {len(gpa_cache)} courses")


# Precompute at startup
precompute_gpas()

# ============================
# SCHEDULE BUILDER API
# ============================

BASE_API_URL = "https://schedulebuilder.umn.edu/api.php"


def get_current_term():
    """Get current semester code - UPDATE THIS EACH SEMESTER"""
    return "1269"  # Spring 2026


def get_course_info(subject, catalog_nbr, campus="UMNTC"):
    """Get course information from Schedule Builder"""
    term = get_current_term()

    try:
        response = requests.get(BASE_API_URL, params={
            'type': 'course',
            'institution': campus,
            'campus': campus,
            'term': term,
            'subject': subject,
            'catalog_nbr': catalog_nbr
        }, timeout=10)

        if response.status_code == 200:
            return response.json()
        return None

    except Exception as e:
        print(f"Error fetching course: {e}")
        return None


def get_course_sections(subject, catalog_nbr, campus="UMNTC"):
    """Get section information from Schedule Builder"""
    term = get_current_term()

    try:
        response = requests.get(BASE_API_URL, params={
            'type': 'sections',
            'institution': campus,
            'campus': campus,
            'term': term,
            'subject': subject,
            'catalog_nbr': catalog_nbr
        }, timeout=10)

        if response.status_code == 200:
            return response.json()
        return None

    except Exception as e:
        print(f"Error fetching sections: {e}")
        return None


# ============================
# HELPER FUNCTIONS FOR GRADES
# ============================

def calculate_gpa_for_course(course_name):
    """Calculate average GPA for a course (uses cache)"""
    if course_name in gpa_cache:
        return gpa_cache[course_name]
    return 0, {}


def format_grade_distribution(grade_dist):
    """Format grade distribution as percentages"""
    total = sum(grade_dist.values())
    if total == 0:
        return "No grade data available"

    result = []
    for grade in ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'F']:
        if grade in grade_dist and grade_dist[grade] > 0:
            count = grade_dist[grade]
            pct = (count / total) * 100
            result.append(f"{grade}: {pct:.1f}% ({count} students)")

    return "\n".join(result) if result else "No grade data available"


def has_open_seats(sections_info):
    """Check if a course has open seats"""
    sections = []
    if isinstance(sections_info, list):
        sections = sections_info
    elif isinstance(sections_info, dict):
        sections = sections_info.get('sections', [])

    for section in sections:
        if isinstance(section, dict):
            enrolled = section.get('enrollment_total', section.get('enrolled', 0))
            capacity = section.get('class_capacity', section.get('capacity', 0))
            try:
                if int(enrolled) < int(capacity):
                    return True
            except:
                pass
    return False


# ============================
# BOT EVENTS
# ============================

@bot.event
async def on_ready():
    print(f"🔥 Logged in as {bot.user}")
    print(f"📊 Loaded {len(df):,} grade records")
    print(f"📅 Current term: {get_current_term()}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


# ============================
# GRADE COMMANDS (CSV DATA)
# ============================

@bot.command()
async def grade(ctx, *, course_name: str):
    """
    Show historical grade distribution for a course
    Usage: !grade CSCI 1133
    """
    course_name = course_name.upper().strip()

    matches = df[df['FULL_NAME'] == course_name]

    if matches.empty:
        await ctx.send(f"❌ Course **{course_name}** not found in historical data.")
        return

    avg_gpa, grade_dist = calculate_gpa_for_course(course_name)
    dist_text = format_grade_distribution(grade_dist)

    sections = matches['CLASS_SECTION'].nunique()
    total_students = matches['GRADE_HDCNT'].sum()

    embed = discord.Embed(title=f"📚 {course_name}", color=discord.Color.gold())
    embed.add_field(name="Historical Average GPA", value=f"{avg_gpa:.2f}", inline=False)
    embed.add_field(name="Total Students (All Time)", value=f"{total_students:,}", inline=True)
    embed.add_field(name="Historical Sections", value=str(sections), inline=True)
    embed.add_field(name="Grade Distribution", value=dist_text, inline=False)

    await ctx.send(embed=embed)


@bot.command()
async def instructor(ctx, *, course_name: str):
    """
    Find historical instructors for a course
    Usage: !instructor CSCI 1133
    """
    course_name = course_name.upper().strip()
    course_data = df[df['FULL_NAME'] == course_name]

    if course_data.empty:
        await ctx.send(f"❌ Course **{course_name}** not found.")
        return

    grade_points = {
        'A+': 4.0, 'A': 4.0, 'A-': 3.67,
        'B+': 3.33, 'B': 3.0, 'B-': 2.67,
        'C+': 2.33, 'C': 2.0, 'C-': 1.67,
        'D+': 1.33, 'D': 1.0, 'F': 0.0
    }

    instructors = {}
    for instructor in course_data['HR_NAME'].dropna().unique():
        instructor_data = course_data[course_data['HR_NAME'] == instructor]

        total_points = 0
        total_students = 0

        for _, row in instructor_data.iterrows():
            grade = row['CRSE_GRADE_OFF']
            count = int(row['GRADE_HDCNT'])
            if grade in grade_points:
                total_points += grade_points[grade] * count
                total_students += count

        instructor_gpa = total_points / total_students if total_students > 0 else 0
        sections = instructor_data['CLASS_SECTION'].nunique()
        instructors[instructor] = (instructor_gpa, sections)

    result = []
    for instructor, (gpa, sections) in sorted(instructors.items(), key=lambda x: x[1][0], reverse=True)[:10]:
        result.append(f"**{instructor}**: {gpa:.2f} GPA ({sections} sections)")

    embed = discord.Embed(title=f"👨‍🏫 Instructors for {course_name}", color=discord.Color.blue())
    embed.description = "\n".join(result) if result else "No instructor data available"

    await ctx.send(embed=embed)


@bot.command()
async def search(ctx, *, keyword: str):
    """
    Search for courses by name or description
    Usage: !search algorithms
    """
    keyword = keyword.upper().strip()

    # 1. Filter unique courses to make searching faster
    # We create a temporary DataFrame of unique courses to avoid searching
    # through thousands of duplicate rows (one for every grade/section)
    unique_courses = df.drop_duplicates(subset=['FULL_NAME'])

    # 2. Search in both the Course Name and the Description
    matches = unique_courses[
        (unique_courses['FULL_NAME'].str.contains(keyword, na=False, case=False)) |
        (unique_courses['DESCR'].str.contains(keyword, na=False, case=False))
        ]

    if matches.empty:
        await ctx.send(f"❌ No courses found matching **{keyword}**")
        return

    # 3. Sort matches alphabetically
    sorted_matches = matches.sort_values('FULL_NAME')
    match_count = len(sorted_matches)

    # 4. Format the output
    # We limit to 15 results to keep the embed clean and readable
    limit = 15
    result_list = []
    for _, row in sorted_matches.head(limit).iterrows():
        # Truncate description if it's too long
        descr = row['DESCR']
        if len(descr) > 60:
            descr = descr[:57] + "..."
        result_list.append(f"**{row['FULL_NAME']}**: {descr}")

    result_text = "\n".join(result_list)

    embed = discord.Embed(
        title=f"🔍 Search Results for '{keyword}'",
        color=discord.Color.green()
    )
    embed.description = f"Found **{match_count}** matches:\n\n{result_text}"

    if match_count > limit:
        embed.set_footer(text=f"Showing {limit} of {match_count} results. Try being more specific!")

    await ctx.send(embed=embed)


@bot.command()
async def easy(ctx, limit: int = 10):
    """
    Find easiest courses by GPA
    Usage: !easy 15
    """
    # Use precomputed cache
    sorted_courses = sorted(gpa_cache.items(), key=lambda x: x[1][0], reverse=True)

    # Filter out courses with 0 GPA
    valid_courses = [(course, gpa, dist) for course, (gpa, dist) in sorted_courses if gpa > 0]

    top_courses = valid_courses[:limit]

    result = [f"**{course}**: {gpa:.2f}" for course, gpa, _ in top_courses]

    embed = discord.Embed(title=f"📈 Top {limit} Easiest Courses (by GPA)", color=discord.Color.green())
    embed.description = "\n".join(result)

    await ctx.send(embed=embed)


@bot.command()
async def hard(ctx, limit: int = 10):
    """
    Find hardest courses by GPA
    Usage: !hard 15
    """
    # Use precomputed cache
    sorted_courses = sorted(gpa_cache.items(), key=lambda x: x[1][0])

    # Filter out courses with 0 GPA
    valid_courses = [(course, gpa, dist) for course, (gpa, dist) in sorted_courses if gpa > 0]

    bottom_courses = valid_courses[:limit]

    result = [f"**{course}**: {gpa:.2f}" for course, gpa, _ in bottom_courses]

    embed = discord.Embed(title=f"📉 Top {limit} Hardest Courses (by GPA)", color=discord.Color.red())
    embed.description = "\n".join(result)

    await ctx.send(embed=embed)


@bot.command()
async def department(ctx, dept: str):
    """
    List courses in a department
    Usage: !department CSCI
    """
    dept = dept.upper()
    dept_courses = df[df['SUBJECT'] == dept]['FULL_NAME'].unique()

    if len(dept_courses) == 0:
        await ctx.send(f"❌ No courses found in department **{dept}**")
        return

    result = ", ".join(sorted(dept_courses)[:50])

    embed = discord.Embed(title=f"📂 {dept} Courses", color=discord.Color.purple())
    embed.description = result
    if len(dept_courses) > 50:
        embed.set_footer(text=f"Showing 50 of {len(dept_courses)} courses")

    await ctx.send(embed=embed)


@bot.command()
async def compare(ctx, *, args: str):
    """
    Compare two courses
    Usage: !compare CSCI 1133, CSCI 2033
    """
    # Split by comma to allow for spaces within course names
    if "," not in args:
        await ctx.send("❌ Please separate courses with a comma. (e.g., `!compare CSCI 1133, CSCI 2033`)")
        return

    parts = [p.strip().upper() for p in args.split(",")]
    if len(parts) < 2:
        await ctx.send("❌ Please provide two courses.")
        return

    course1, course2 = parts[0], parts[1]

    gpa1, dist1 = calculate_gpa_for_course(course1)
    gpa2, dist2 = calculate_gpa_for_course(course2)

    if gpa1 == 0 or gpa2 == 0:
        missing = []
        if gpa1 == 0: missing.append(course1)
        if gpa2 == 0: missing.append(course2)
        await ctx.send(f"❌ Data not found for: {', '.join(missing)}")
        return

    # Calculate total students for context
    students1 = df[df['FULL_NAME'] == course1]['GRADE_HDCNT'].sum()
    students2 = df[df['FULL_NAME'] == course2]['GRADE_HDCNT'].sum()

    embed = discord.Embed(title="⚖️ Course Comparison", color=discord.Color.orange())

    # Adding a comparison visual
    diff = gpa1 - gpa2
    comparison_msg = f"{course1} is {'easier' if diff > 0 else 'harder'} by {abs(diff):.2f} GPA points."

    embed.add_field(name=f"📘 {course1}", value=f"**GPA: {gpa1:.2f}**\nStudents: {students1:,}", inline=True)
    embed.add_field(name=f"📙 {course2}", value=f"**GPA: {gpa2:.2f}**\nStudents: {students2:,}", inline=True)
    embed.set_footer(text=comparison_msg)

    await ctx.send(embed=embed)


@bot.command()
async def stats(ctx, *, course_name: str):
    """
    Detailed course statistics
    Usage: !stats CSCI 1133
    """
    course_name = course_name.upper().strip()
    course_data = df[df['FULL_NAME'] == course_name]

    if course_data.empty:
        await ctx.send(f"❌ Course **{course_name}** not found.")
        return

    gpa, grade_dist = calculate_gpa_for_course(course_name)
    sections = course_data['CLASS_SECTION'].nunique()
    total_students = course_data['GRADE_HDCNT'].sum()
    instructors = course_data['HR_NAME'].nunique()

    embed = discord.Embed(title=f"📊 Statistics for {course_name}", color=discord.Color.blue())
    embed.add_field(name="Average GPA", value=f"{gpa:.2f}", inline=True)
    embed.add_field(name="Total Students", value=f"{total_students:,}", inline=True)
    embed.add_field(name="Total Sections", value=str(sections), inline=True)
    embed.add_field(name="Instructors", value=str(instructors), inline=True)

    await ctx.send(embed=embed)


# ============================
# SCHEDULE BUILDER COMMANDS
# ============================

@bot.command()
async def schedule(ctx, *, course_name: str):
    """
    Get current semester schedule from Schedule Builder
    Usage: !schedule CSCI 1133
    """
    course_name = course_name.upper().strip()
    parts = course_name.split()

    if len(parts) < 2:
        await ctx.send("❌ Please provide subject and course number (e.g., `!schedule CSCI 1133`)")
        return

    subject = parts[0]
    catalog_nbr = parts[1]

    await ctx.send(f"🔍 Searching Schedule Builder for **{course_name}**...")

    course_info = get_course_info(subject, catalog_nbr)

    if not course_info:
        await ctx.send(f"❌ Could not find **{course_name}** in Schedule Builder")
        return

    sections = get_course_sections(subject, catalog_nbr)

    embed = discord.Embed(
        title=f"📅 {subject} {catalog_nbr}",
        color=discord.Color.blue()
    )

    if isinstance(course_info, dict):
        embed.description = course_info.get('title', course_info.get('descr', 'No description'))

        if 'credits' in course_info:
            embed.add_field(name="Credits", value=course_info['credits'], inline=True)

        if 'grading' in course_info:
            embed.add_field(name="Grading", value=course_info['grading'], inline=True)

    if sections:
        if isinstance(sections, list):
            embed.add_field(name="Sections Available", value=str(len(sections)), inline=True)
        elif isinstance(sections, dict) and 'sections' in sections:
            embed.add_field(name="Sections Available", value=str(len(sections['sections'])), inline=True)

    embed.set_footer(text=f"Term: {get_current_term()}")

    await ctx.send(embed=embed)


@bot.command()
async def sections(ctx, *, course_name: str):
    """
    Get detailed section information
    Usage: !sections CSCI 1133
    """
    course_name = course_name.upper().strip()
    parts = course_name.split()

    if len(parts) < 2:
        await ctx.send("❌ Please provide subject and course number")
        return

    subject = parts[0]
    catalog_nbr = parts[1]

    sections_data = get_course_sections(subject, catalog_nbr)

    if not sections_data:
        await ctx.send(f"❌ Could not find sections for **{course_name}**")
        return

    sections = []
    if isinstance(sections_data, list):
        sections = sections_data
    elif isinstance(sections_data, dict):
        sections = sections_data.get('sections', [])

    if not sections:
        await ctx.send(f"❌ No sections available for **{course_name}** this semester")
        return

    section_text = []
    for i, section in enumerate(sections[:8]):
        if isinstance(section, dict):
            section_num = section.get('section', section.get('class_section', 'N/A'))
            instructor = section.get('instructors', section.get('instructor', 'TBA'))

            if isinstance(instructor, list):
                instructor = ", ".join(instructor)

            days = section.get('days', 'TBA')
            start_time = section.get('start_time', '')
            end_time = section.get('end_time', '')
            time = f"{start_time}-{end_time}" if start_time and end_time else 'TBA'

            location = section.get('location', section.get('room', 'TBA'))
            enrollment = section.get('enrollment_total', section.get('enrolled', 'N/A'))
            capacity = section.get('class_capacity', section.get('capacity', 'N/A'))

            section_text.append(
                f"**Section {section_num}**\n"
                f"👨‍🏫 {instructor}\n"
                f"🕐 {days} {time}\n"
                f"📍 {location}\n"
                f"👥 {enrollment}/{capacity} enrolled\n"
            )

    if len(section_text) > 4:
        embed1 = discord.Embed(
            title=f"📋 Sections for {course_name} (Part 1)",
            description="\n".join(section_text[:4]),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed1)

        embed2 = discord.Embed(
            title=f"📋 Sections for {course_name} (Part 2)",
            description="\n".join(section_text[4:]),
            color=discord.Color.green()
        )
        if len(sections) > 8:
            embed2.set_footer(text=f"Showing 8 of {len(sections)} sections")
        await ctx.send(embed=embed2)
    else:
        embed = discord.Embed(
            title=f"📋 Sections for {course_name}",
            description="\n".join(section_text),
            color=discord.Color.green()
        )
        if len(sections) > 8:
            embed.set_footer(text=f"Showing 8 of {len(sections)} sections")
        await ctx.send(embed=embed)


@bot.command()
async def full(ctx, *, course_name: str):
    """
    Complete course info: historical grades + current schedule
    Usage: !full CSCI 1133
    """
    course_name = course_name.upper().strip()

    # Get grade data
    gpa, grade_dist = calculate_gpa_for_course(course_name)
    course_data = df[df['FULL_NAME'] == course_name]

    # Get schedule data
    parts = course_name.split()
    schedule_info = None
    sections_info = None

    if len(parts) >= 2:
        schedule_info = get_course_info(parts[0], parts[1])
        sections_info = get_course_sections(parts[0], parts[1])

    embed = discord.Embed(
        title=f"📊 Complete Analysis: {course_name}",
        color=discord.Color.gold()
    )

    # Historical grade data
    if gpa > 0:
        embed.add_field(name="📈 Historical Avg GPA", value=f"**{gpa:.2f}**", inline=True)

        if grade_dist:
            top_grade = max(grade_dist, key=grade_dist.get)
            embed.add_field(name="🎯 Most Common Grade", value=f"**{top_grade}**", inline=True)

        if not course_data.empty:
            total_students = course_data['GRADE_HDCNT'].sum()
            embed.add_field(name="👥 Total Historical Students", value=f"**{total_students:,}**", inline=True)

    # Current schedule data
    if schedule_info and isinstance(schedule_info, dict):
        if 'credits' in schedule_info:
            embed.add_field(name="💳 Credits", value=schedule_info['credits'], inline=True)

    if sections_info:
        sections = []
        if isinstance(sections_info, list):
            sections = sections_info
        elif isinstance(sections_info, dict):
            sections = sections_info.get('sections', [])

        if sections:
            embed.add_field(name="📅 Current Sections", value=f"**{len(sections)}** available", inline=True)

            open_sections = 0
            for section in sections:
                if isinstance(section, dict):
                    enrolled = section.get('enrollment_total', section.get('enrolled', 0))
                    capacity = section.get('class_capacity', section.get('capacity', 0))
                    try:
                        if int(enrolled) < int(capacity):
                            open_sections += 1
                    except:
                        pass

            if open_sections > 0:
                embed.add_field(name="✅ Open Sections", value=f"**{open_sections}**", inline=True)

    # Grade distribution
    if grade_dist:
        dist_text = format_grade_distribution(grade_dist)
        if len(dist_text) > 1024:
            dist_text = dist_text[:1020] + "..."
        embed.add_field(name="📊 Grade Distribution", value=dist_text, inline=False)

    embed.set_footer(text=f"Term: {get_current_term()} | Use !sections {course_name} for detailed info")

    await ctx.send(embed=embed)


# ============================
# NEW COMBINED COMMANDS
# ============================

@bot.command()
async def pick(ctx, dept: str, difficulty: str = "easy"):
    """
    Show easy/hard courses in a department that are offered this semester
    Usage: !pick CSCI easy
    Usage: !pick MATH hard
    """
    dept = dept.upper()
    difficulty = difficulty.lower()

    if difficulty not in ["easy", "hard"]:
        await ctx.send("❌ Difficulty must be either 'easy' or 'hard'")
        return

    await ctx.send(f"🔍 Finding {difficulty} **{dept}** courses offered this semester...")

    # Get all courses in department with their GPAs from cache
    dept_courses = [(course, gpa, dist) for course, (gpa, dist) in gpa_cache.items()
                    if course.startswith(dept + " ") and gpa > 0]

    if len(dept_courses) == 0:
        await ctx.send(f"❌ No courses found in department **{dept}**")
        return

    # Sort by difficulty
    if difficulty == "easy":
        sorted_courses = sorted(dept_courses, key=lambda x: x[1], reverse=True)
    else:
        sorted_courses = sorted(dept_courses, key=lambda x: x[1])

    # Check which ones are offered this semester
    available_courses = []
    for course, gpa, dist in sorted_courses[:30]:
        if len(available_courses) >= 10:
            break

        parts = course.split()
        if len(parts) >= 2:
            sections = get_course_sections(parts[0], parts[1])
            if sections:
                has_seats = has_open_seats(sections)
                available_courses.append((course, gpa, has_seats))

    if not available_courses:
        await ctx.send(f"❌ No {difficulty} **{dept}** courses found that are currently offered")
        return

    # Build result
    result = []
    for course, gpa, has_seats in available_courses:
        seat_emoji = "✅" if has_seats else "🔒"
        result.append(f"{seat_emoji} **{course}**: {gpa:.2f} GPA")

    embed = discord.Embed(
        title=f"{'📈' if difficulty == 'easy' else '📉'} {difficulty.capitalize()} {dept} Courses This Semester",
        description="\n".join(result),
        color=discord.Color.green() if difficulty == "easy" else discord.Color.red()
    )
    embed.set_footer(text="✅ = Open seats | 🔒 = Full")

    await ctx.send(embed=embed)


@bot.command()
async def bestinstructor(ctx, *, course_name: str):
    """
    Show current instructors with their historical GPAs
    Usage: !bestinstructor CSCI 1133
    """
    course_name = course_name.upper().strip()
    parts = course_name.split()

    if len(parts) < 2:
        await ctx.send("❌ Please provide subject and course number")
        return

    subject = parts[0]
    catalog_nbr = parts[1]

    await ctx.send(f"🔍 Finding best instructors for **{course_name}**...")

    # Get current sections
    sections_data = get_course_sections(subject, catalog_nbr)

    if not sections_data:
        await ctx.send(f"❌ Could not find **{course_name}** in Schedule Builder")
        return

    sections = []
    if isinstance(sections_data, list):
        sections = sections_data
    elif isinstance(sections_data, dict):
        sections = sections_data.get('sections', [])

    if not sections:
        await ctx.send(f"❌ No sections available for **{course_name}** this semester")
        return

    # Get current instructors
    current_instructors = set()
    for section in sections:
        if isinstance(section, dict):
            instructor = section.get('instructors', section.get('instructor', ''))
            if isinstance(instructor, list):
                current_instructors.update(instructor)
            elif instructor:
                current_instructors.add(instructor)

    # Get historical data for these instructors
    grade_points = {
        'A+': 4.0, 'A': 4.0, 'A-': 3.67,
        'B+': 3.33, 'B': 3.0, 'B-': 2.67,
        'C+': 2.33, 'C': 2.0, 'C-': 1.67,
        'D+': 1.33, 'D': 1.0, 'F': 0.0
    }

    instructor_stats = {}
    course_data = df[df['FULL_NAME'] == course_name]

    for instructor in current_instructors:
        instructor_data = course_data[course_data['HR_NAME'].str.contains(instructor, case=False, na=False)]

        if instructor_data.empty:
            instructor_stats[instructor] = (0, 0, "No historical data")
            continue

        total_points = 0
        total_students = 0

        for _, row in instructor_data.iterrows():
            grade = row['CRSE_GRADE_OFF']
            count = int(row['GRADE_HDCNT'])
            if grade in grade_points:
                total_points += grade_points[grade] * count
                total_students += count

        instructor_gpa = total_points / total_students if total_students > 0 else 0
        instructor_stats[instructor] = (instructor_gpa, total_students, instructor_gpa)

    # Sort by GPA
    sorted_instructors = sorted(instructor_stats.items(), key=lambda x: x[1][2], reverse=True)

    # Build result
    result = []
    for instructor, (gpa, students, _) in sorted_instructors:
        if gpa > 0:
            result.append(f"⭐ **{instructor}**: {gpa:.2f} GPA ({students} historical students)")
        else:
            result.append(f"❓ **{instructor}**: No historical data")

    embed = discord.Embed(
        title=f"👨‍🏫 Current Instructors for {course_name}",
        description="\n".join(result) if result else "No instructor data available",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Ranked by historical GPA")

    await ctx.send(embed=embed)


@bot.command()
async def openandeasy(ctx, limit: int = 10):
    """
    Show easy classes with open seats this semester
    Usage: !openandeasy 15
    """
    await ctx.send(f"🔍 Finding top {limit} easy courses with open seats... (this may take a moment)")

    # Get courses sorted by GPA from cache
    sorted_courses = sorted(gpa_cache.items(), key=lambda x: x[1][0], reverse=True)

    # Filter for high GPA courses
    high_gpa_courses = [(course, gpa, dist) for course, (gpa, dist) in sorted_courses if gpa >= 3.0]

    # Check which ones have open seats
    results = []
    checked = 0

    for course, gpa, dist in high_gpa_courses:
        if len(results) >= limit:
            break

        checked += 1
        if checked > 100:  # Don't check more than 100 courses
            break

        parts = course.split()
        if len(parts) >= 2:
            sections_info = get_course_sections(parts[0], parts[1])

            if sections_info and has_open_seats(sections_info):
                # Count open seats
                sections = []
                if isinstance(sections_info, list):
                    sections = sections_info
                elif isinstance(sections_info, dict):
                    sections = sections_info.get('sections', [])

                open_count = 0
                total_sections = len(sections)

                for section in sections:
                    if isinstance(section, dict):
                        enrolled = section.get('enrollment_total', section.get('enrolled', 0))
                        capacity = section.get('class_capacity', section.get('capacity', 0))
                        try:
                            if int(enrolled) < int(capacity):
                                open_count += 1
                        except:
                            pass

                results.append((course, gpa, open_count, total_sections))

    if not results:
        await ctx.send("❌ No easy courses with open seats found")
        return

    # Build result
    result_text = []
    for course, gpa, open_count, total_sections in results:
        result_text.append(f"✅ **{course}**: {gpa:.2f} GPA | {open_count}/{total_sections} sections open")

    embed = discord.Embed(
        title=f"🎯 Top {len(results)} Easy Courses with Open Seats",
        description="\n".join(result_text),
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Only showing courses with GPA ≥ 3.0 | Term: {get_current_term()}")

    await ctx.send(embed=embed)
## help command
# First, disable the default help command
bot.remove_command('help')


@bot.command()
async def help(ctx, command_name: str = None):
    """Shows all commands or details for a specific command."""
    embed = discord.Embed(title="🎓 UMN Course Bot Help", color=discord.Color.maroon())

    commands_dict = {
        "grade": ("`!grade <course>`", "Shows historical grade distribution."),
        "search": ("`!search <keyword>`", "Search courses by name or description."),
        "compare": ("`!compare <course1>, <course2>`", "Compare GPAs of two courses."),
        "sections": ("`!sections <course>`", "Shows current open sections."),
        "instructor": ("`!instructor <course>`", "Lists historical GPAs for all professors of a course."),
        "optimize": ("`!optimize <course1>, <course2>...`", "Finds the easiest schedule for a list of courses.")
    }

    if command_name:
        # Help for a specific command
        cmd = command_name.lower()
        if cmd in commands_dict:
            usage, desc = commands_dict[cmd]
            embed.add_field(name=f"Command: {cmd}", value=f"**Usage:** {usage}\n**Description:** {desc}")
        else:
            await ctx.send(f"❌ Command `{command_name}` not found.")
            return
    else:
        # General list
        for name, (usage, desc) in commands_dict.items():
            embed.add_field(name=f"!{name}", value=desc, inline=False)
        embed.set_footer(text="Type !help <command> for usage details.")

    await ctx.send(embed=embed)

# ============================
# RUN BOT
# ============================
bot.run(TOKEN)