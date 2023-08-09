on run argv
	if (count of argv) < 1 then
		set promptType to "file"
		set defaultDirectory to (path to home folder)
		set defaultFilename to "image.jpg"
	else
		set promptType to (item 1 of argv)

		if (count of argv) < 2 then
			set defaultDirectory to (path to home folder)
			set defaultFilename to "image.jpg"
		else
			set defaultDirectory to POSIX file (item 2 of argv)

			if (count of argv) < 3 then
				set defaultFilename to "image.jpg"
			else
				set defaultFilename to (item 3 of argv)
			end if
		end if
	end if

	if promptType = "file" then
		set filename to POSIX path of (choose file with prompt "Choose a file:" default location defaultDirectory)
		return filename as text
	else if promptType = "folder" then
		set directory to POSIX path of (choose folder with prompt "Choose a directory:" default location defaultDirectory)
		return directory as text
	else if promptType = "save" then
		set filename to POSIX path of (choose file name with prompt "Choose file:" default location defaultDirectory default name defaultFilename)
		return filename as text
	else
		display dialog "oops"
	end if
end run