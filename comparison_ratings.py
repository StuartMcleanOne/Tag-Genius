# compare_ratings.py
import xml.etree.ElementTree as ET
import sys
import os


def convert_rating_to_stars(rating_value):
    """Converts a Rekordbox XML rating value to a 1-5 star integer."""
    if not rating_value:
        return 0
    val = int(rating_value)
    if val >= 255: return 5
    if val >= 204: return 4
    if val >= 153: return 3
    if val >= 102: return 2
    if val >= 51: return 1
    return 0


def parse_xml_ratings(filepath):
    """Parses an XML file and returns a dictionary of track ratings."""
    ratings = {}
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        tracks = root.find('COLLECTION').findall('TRACK')
        for track in tracks:
            # Create a unique key for each track
            artist = track.get('Artist', 'Unknown Artist')
            name = track.get('Name', 'Unknown Track')
            key = f"{artist} - {name}"

            rating = track.get('Rating')
            ratings[key] = convert_rating_to_stars(rating)
    except (ET.ParseError, FileNotFoundError) as e:
        print(f"Error parsing file {filepath}: {e}")
    return ratings


def compare_ratings(your_ratings, ai_ratings):
    """Compares the two sets of ratings and prints a table."""

    print("\n--- AI vs. Your Ratings Comparison ---\n")
    print(f"{'Track':<60} | {'Your Rating':<12} | {'AI Rating':<10} | {'Difference'}")
    print("-" * 100)

    total_diff = 0
    exact_matches = 0

    all_tracks = sorted(your_ratings.keys())

    for track_key in all_tracks:
        your_score = your_ratings.get(track_key, 0)
        ai_score = ai_ratings.get(track_key, 0)

        diff = abs(your_score - ai_score)
        total_diff += diff

        if diff == 0:
            exact_matches += 1
            diff_str = "✔"  # Exact match
        else:
            diff_str = f"{'-' if ai_score < your_score else '+'}{diff}"

        # Truncate long track names for display
        display_name = (track_key[:57] + '...') if len(track_key) > 60 else track_key

        print(f"{display_name:<60} | {your_score:<12} | {ai_score:<10} | {diff_str}")

    print("-" * 100)
    avg_diff = total_diff / len(all_tracks) if all_tracks else 0
    match_percentage = (exact_matches / len(all_tracks)) * 100 if all_tracks else 0
    print(f"\nSummary:")
    print(f"Exact Matches: {exact_matches} / {len(all_tracks)} ({match_percentage:.2f}%)")
    print(f"Average Difference: {avg_diff:.2f} stars")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_ratings.py <your_original_xml> <ai_generated_xml>")
        sys.exit(1)

    original_file = sys.argv[1]
    ai_file = sys.argv[2]

    if not os.path.exists(original_file):
        print(f"Error: File not found at {original_file}")
        sys.exit(1)

    if not os.path.exists(ai_file):
        print(f"Error: File not found at {ai_file}")
        sys.exit(1)

    your_ratings = parse_xml_ratings(original_file)
    ai_ratings = parse_xml_ratings(ai_file)

    compare_ratings(your_ratings, ai_ratings)