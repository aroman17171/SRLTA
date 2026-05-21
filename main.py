from src.analysis import load_lap, plot_all

if __name__ == "__main__":
    lap1 = load_lap("data/lap1.csv")
    lap2 = load_lap("data/lap2.csv")

    plot_all(lap1, lap2)