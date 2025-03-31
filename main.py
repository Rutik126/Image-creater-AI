from fastcore.parallel import threaded
from fasthtml.common import *
import uuid, os, uvicorn, requests, glob
from PIL import Image
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("HUGGINGFACE_API_KEY")
API_URL = "https://api-inference.huggingface.co/models/alvdansen/littletinies"
headers = {"Authorization": f"Bearer {API_KEY}"}

# Function to query the Hugging Face API
def query(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.content

# Database setup
tables = database('data/gens.db').t
gens = tables.gens
if not gens in tables:
    gens.create(prompt=str, id=int, folder=str, pk='id')
Generation = gens.dataclass()

# Flexbox CSS (http://flexboxgrid.com/)
gridlink = Link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/flexboxgrid/6.3.1/flexboxgrid.min.css", type="text/css")

# Our FastHTML app
app = FastHTML(hdrs=(picolink, gridlink))

# Main page
@app.get("/")
def home():
    inp = Input(id="new-prompt", name="prompt", placeholder="Enter a prompt")
    add = Form(Group(inp, Button("Generate")), hx_post="/", target_id='gen-list', hx_swap="afterbegin")
    gen_containers = [generation_preview(g) for g in gens(limit=2)]  # Start with last 2
    gen_list = Div(*reversed(gen_containers), id='gen-list', cls="row")  # flexbox container: class = row

    # Display the number of images
    image_count_div = Div(id='image-count', hx_get="/image_count", hx_trigger="load", hx_swap="innerHTML")

    return Title('Image Generation Demo'), Main(
        H1('Magic Image Generation'),
        add,
        image_count_div,  # Add the image count display
        gen_list,
        cls='container'
    )

# Show the image (if available) and prompt for a generation
def generation_preview(g):
    grid_cls = "box col-xs-12 col-sm-6 col-md-4 col-lg-3"
    image_path = f"{g.folder}/{g.id}.png"
    delete_button = Button("Delete", hx_delete=f"/gens/{g.id}", hx_confirm="Are you sure you want to delete this image?", hx_target=f'#gen-{g.id}', hx_swap="outerHTML", hx_trigger="click")
    if os.path.exists(image_path):
        return Div(Card(
                       Img(src=image_path, alt="Card image", cls="card-img-top"),
                       Div(P(B("Prompt: "), g.prompt, cls="card-text"), cls="card-body"),
                       delete_button
                   ), id=f'gen-{g.id}', cls=grid_cls)
    return Div(f"Generating gen {g.id} with prompt {g.prompt}",
            id=f'gen-{g.id}', hx_get=f"/gens/{g.id}",
            hx_trigger="every 2s", hx_swap="outerHTML", cls=grid_cls)

# A pending preview keeps polling this route until we return the image preview
@app.get("/gens/{id}")
def preview(id:int):
    return generation_preview(gens.get(id))

# For images, CSS, etc.
@app.get("/{fname:path}.{ext:static}")
def static(fname:str, ext:str):
    return FileResponse(f'{fname}.{ext}')

# Generation route
@app.post("/")
def post(prompt:str):
    if count_free_images() >= 2:
        return "Free limit reached! <a href='https://example.com/upgrade'>Upgrade Now</a>"

    folder = f"data/gens/{str(uuid.uuid4())}"
    os.makedirs(folder, exist_ok=True)
    g = gens.insert(Generation(prompt=prompt, folder=folder))
    generate_and_save(g.prompt, g.id, g.folder)
    clear_input = Input(id="new-prompt", name="prompt", placeholder="Enter a prompt", hx_swap_oob='true')
    return generation_preview(g), clear_input

# Delete route
@app.delete("/gens/{id}")
def delete_gen(id:int):
    gen = gens.get(id)
    if gen:
        image_path = f"{gen.folder}/{gen.id}.png"
        if os.path.exists(image_path):
            os.remove(image_path)
        gens.delete(id)
    return "Hit Refresh!"

# Generate an image and save it to the folder (in a separate thread)
@threaded
def generate_and_save(prompt, id, folder):
    image_bytes = query({"inputs": prompt})
    image = Image.open(io.BytesIO(image_bytes))
    image.save(f"{folder}/{id}.png")
    return True

# Count PNG images
@app.get("/image_count")
def image_count():
    count = count_free_images()
    if count >= 2:
        return "Free limit reached! <a href='https://example.com/upgrade'>Upgrade Now</a>"
    return f"Number of images generated: {count}/2"

def count_free_images():
    png_files = glob.glob("data/gens/**/*.png", recursive=True)
    return len(png_files)

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=int(os.getenv("PORT", default=8000)))
