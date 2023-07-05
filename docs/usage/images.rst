Images
======

PicPocket stores information about your images, but not the image files themselves. To quote the most ominous Windows screen "All your files are exactly where you left them". PicPocket stores the following information about your images:

creator
    Who created the image. If you haven't already told PicPocket who created an image, it will try to derive this from the Author field of the image's EXIF data.

title
    A title for the image.

caption
    A caption for the image. PicPocket will attempt to derive a default caption from the ImageDescription field of the image's EXIF data.

alt
    Descriptive text for the image.

rating
    How good you think the image is. Ratings must be whole numbers, but are otherwise unrestricted.

tags
    Any :doc:`tags <tags>` you want to apply to the image.

Additionally, PicPocket stores the following derived information about the image for its own uses:

path
    The path to the image. Internally, PicPocket stores the image path relative to its location, but it will work out the full path when displaying image info whenever it can.

hash
    A number representing the contents of the file

creation date
    When the image was made. If possible, this will be pulled from EXIF data. If that isn't possible, it will assume the creation date and the last-modified date are the same.

last-modified date
    When the image was last changed (edited, created, etc.).

dimensions
    The size of the image.

exif
    A subset of the EXIF data stored within the image. Presently, PicPocket only stores the fields that are numbers or text and doesn't store any binary fields. GPS data is not currently stored.

Actions
-------

Search
    Find images based on their tags and/or properties.

Upload
    Add a copy of an image to PicPocket at a desired location.

Find
    Find an image in PicPocket given its filepath

Edit
    Modify user-supplied information about images (including tags).

Move
    Move the image file to a different place. This moves the actual file, it does not copy it to the new location.

Remove
    By default, this removes the image from PicPocket without deleting the actual image file.

Verify
    Check that images in PicPocket still exist at their expected locations, and update any derived information that may have changed. Verify will return the set of images that should be available but can't be found.

    By default, derived information is only updated if the file has been modified. Verify adds an option to reparse EXIF data even if the image hasn't changed, as PicPocket does not currently store all EXIF data.