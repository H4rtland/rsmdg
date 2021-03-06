from flask import Blueprint, render_template, flash, request, jsonify, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename

import random
import time
import os
import os.path as op
from collections import OrderedDict
from operator import itemgetter
import inspect
import json
from datetime import datetime

import plotly
import plotly.graph_objs as go

from detector.detector import Path, path_passes_through_cube

from result.models import Result, ResultStatus
from analysis.analysis import Analysis

from app import RESULTS_FOLDER, db

result = Blueprint("result", __name__)

@result.route("/upload_result", methods=["GET", "POST"])
def upload_result():
    """
    Route to upload result file to database
    POST with requests.post("http://127.0.0.1:5000/upload_result", files={"field_name":open("path/to/file", "r")})
    :return: HTTP response
    """
    if len(request.files) == 0:
        return jsonify(success=False), 400

    file = next(request.files.values())
    filename = secure_filename(file.filename)
    file.save(op.join(RESULTS_FOLDER, filename))

    result = Result()
    result.file = op.join(RESULTS_FOLDER, filename)

    result.detector_start_time = datetime.fromtimestamp(float(request.form["detector_start_time"]))
    result.detector_end_time = datetime.fromtimestamp(float(request.form["detector_end_time"]))

    db.session.add(result)
    db.session.commit()

    return jsonify(success=True, result_id=result.id), 200

@result.route("/results")
def result_list():
    results = Result.query.all()[::-1]
    return render_template("result_list.html", results=results)

@result.route("/result/<int:result_id>")
def result_page(result_id):
    """
    todo: comment on individual results
    """
    result = Result.query.get(result_id)

    parameters = result.parameters
    argspec = inspect.getfullargspec(Analysis.active_analysis.analyse)
    kwargs = dict(zip(argspec.args[-len(argspec.defaults):], argspec.defaults))
    for name, value in kwargs.items():
        if name not in parameters:
            parameters[name] = value

    # Remove old parameters
    for name in list(parameters.keys()):
        if name not in kwargs:
            del parameters[name]

    parameters = OrderedDict(sorted(parameters.items(), key=itemgetter(0)))

    def parameter_type(parameter):
        if type(parameters[parameter]) is bool:
            return "checkbox"
        return "text"


    plots = []
    plot_priority = ["pulses_histogram", "path_track", "density_slice", "density_dist"]
    if not result.failed:
        for plot_name in plot_priority:
            plot = result.get_plot(plot_name)
            if not plot is None:
                plots.append((plot_name, plot))

    return render_template("result.html", result=result, plots=plots, parameters=parameters, parameter_type=parameter_type)

@result.route("/jump_to_result", methods=["GET", "POST"])
def jump_to_result():
    result_id = request.form["jump_to_id"]
    if not result_id.isdigit():
        flash("Could not find result with that ID", "error")
        return redirect(url_for("result.result_list"))
    result = Result.query.get(result_id)
    if result is None:
        flash("Could not find result with that ID", "error")
        return redirect(url_for("result.result_list"))
    return redirect(url_for("result.result_page", result_id=result.id))

@result.route("/reanalyse/<int:result_id>", methods=["GET", "POST"])
def reanalyse(result_id):
    result = Result.query.get(result_id)
    result.clear_plots()
    argspec = inspect.getfullargspec(Analysis.active_analysis.analyse)
    kwargs = dict(zip(argspec.args[-len(argspec.defaults):], argspec.defaults))
    parameters = result.parameters
    for name, value in request.form.items():
        if len(value) > 0:
            if name in kwargs:
                parameters[name] = type(kwargs[name])(value)


    result.parameters = parameters
    result.status = ResultStatus.pending
    db.session.commit()
    return redirect(url_for("result.result_page", result_id=result_id))

@result.route("/download_data_file/<int:result_id>")
def download_data_file(result_id):
    # for name in dir(request):
    #     if not name.startswith("__"):
    #         print(name, getattr(request, name))
    result = Result.query.get(result_id)
    if result is None:
        flash("Result {} does not exist".format(result_id), "error")
        return redirect(request.referrer)
    if not op.exists(result.file):
        flash("Data file ({}) no longer exists on the server".format(result.file), "error")
        return redirect(request.referrer)
    return send_from_directory(directory=RESULTS_FOLDER, filename=result.filename, attachment_filename="result-{}-datafile.txt".format(result_id), as_attachment=True)

@result.route("/check_progress/<int:result_id>")
def check_progress(result_id):
    state = request.args.get("current_status", "complete")
    result = Result.query.get(result_id)
    reload = result.status.name != state
    return jsonify(dict(reload=reload))


@result.route("/result_example")
def example_result():
    """
    idea: cache plotly html files, offer "replot" on result page
    idea: when path start/end are quantized, cache volume check results
    todo: move analysis code out of view
    """

    start_time = time.perf_counter()
    #p = Path(0.55, 0.55, 1, 0.55, 0.55, 0)
    #print(path_passes_through_cube(p, 0.6, 0.6, 0.6, 0.1, 0.1, 0.1))

    lines = []
    #xs = []
    #ys = []
    #zs = []
    st = time.time()
    # 10000 Request time: 69.24448532398439 with obstruction
    # 10000 Request time: 70.08756806654017 without obstruction
    # 10000 Request time: 7.622724069724689 with easy checks
    # 100000 Request time: 729.9082427835476 without caching
    # 100000 Request time: 754.6030013966841 with caching
    # 100000 Request time: 76.17804744634259 with easy checks
    while len(lines) < 800000:
        # xi, yi, zi = random.random(), random.random(), 1
        # xf, yf, zf = xi+(random.random()-0.5), yi+(random.random()-0.5), 0
        xi, yi, zi = round(0.05 + 0.1*random.randint(0, 9), 2), round(0.05 + 0.1*random.randint(0, 9), 2), 1
        #xf, yf, zf = 0.02 + 0.04*random.randint(0, 24), 0.02 + 0.04*random.randint(0, 24), 0
        #xi, yi, zi = random.random(), random.random(), 1
        #xf, yf, zf = xi+(random.random()-0.5)/2, yi+(random.random()-0.5)/2, 0
        xf, yf, zf = round(xi+(0.1*random.randint(0, 6)-0.3), 2), round(yi+(0.1*random.randint(0, 6)-0.3), 2), 0
        if (0 < xf < 1) and (0 < yf < 1):
            p = Path(xi, yi, zi, xf, yf, zf)
            if path_passes_through_cube(p, 0.30, 0.40, 0.0, 0.2, 0.2, 0.2) and random.random() > 0.2:
                continue
            if path_passes_through_cube(p, 0.50, 0.40, 0.0, 0.2, 0.2, 0.2) and random.random() > 0.6:
                continue
            lines.append(([xi, xf], [yi, yf], [zi, zf]))
            #xs += [xi, xf, None]
            #ys += [yi, yf, None]
            #zs += [zi, zf, None]
            #lines.append(None)

    print("Random generation time: {}".format(time.time()-st))

    datas = []
    col = '#1f77b4'
    xs = []
    ys = []
    zs = []
    paths_shown = 0
    for line in lines:
        if random.random() > (400/len(lines)):
            continue
        xs += line[0] + [None,]
        ys += line[1] + [None,]
        zs += line[2] + [None,]
        paths_shown += 1
    datas.append(
        go.Scatter3d(x=xs, y=ys, z=zs,
                        hoverinfo="none",
                        connectgaps=False,
                        marker=dict(
                            size=4,
                            color=zs,
                            colorscale='Viridis',
                        ),
                        line=dict(
                            color=col,
                            width=1
                        ),
                     )
    )



    """for line in lines:
        if random.random() > (200/len(lines)):
            continue
        col = '#1f77b4'
        p = Path(line[0][0], line[1][0], line[2][0], line[0][1], line[1][1], line[2][1])
        if path_passes_through_cube(p, 0.5, 0.5, 0.5, 0.1, 0.1, 0.1):
            col = "#ff0000"
        datas.append(go.Scatter3d(
            x=line[0], y=line[1], z=line[2],
            marker=dict(
                size=4,
                color=line[2],
                colorscale='Viridis',
            ),
            line=dict(
                color=col,
                width=1
            ),
            hoverinfo="none",
        ))"""

    x = [(0.4, 0.6), (0.6, 0.6), (0.6, 0.4), (0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4), (0.4, 0.4), (0.4, 0.4), (0.6, 0.6), (0.4, 0.4), (0.6, 0.6)]
    y = [(0.4, 0.4), (0.4, 0.4), (0.4, 0.4), (0.4, 0.4), (0.6, 0.6), (0.6, 0.6), (0.6, 0.6), (0.6, 0.6), (0.4, 0.6), (0.4, 0.6), (0.4, 0.6), (0.4, 0.6)]
    z = [(0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4), (0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4), (0.4, 0.4), (0.4, 0.4), (0.6, 0.6), (0.6, 0.6)]

    for i in range(0, len(x)):
        datas.append(go.Scatter3d(
            x=x[i], y=y[i], z=z[i],
            marker=dict(
                size=2,
                color="#0000ff",
            ),
            line=dict(
                color="#0000ff",
                width=1
            ),
            hoverinfo="none",
        ))

    layout = dict(
        width=700,
        height=700,
        autosize=False,
        title='muon paths',
        showlegend = False,
        scene=dict(
            xaxis=dict(
                gridcolor='rgb(255, 255, 255)',
                zerolinecolor='rgb(255, 255, 255)',
                showbackground=True,
                backgroundcolor='rgb(230, 230,230)',
                range=[0, 1],
            ),
            yaxis=dict(
                gridcolor='rgb(255, 255, 255)',
                zerolinecolor='rgb(255, 255, 255)',
                showbackground=True,
                backgroundcolor='rgb(230, 230,230)',
                range=[0, 1],
            ),
            zaxis=dict(
                gridcolor='rgb(255, 255, 255)',
                zerolinecolor='rgb(255, 255, 255)',
                showbackground=True,
                backgroundcolor='rgb(230, 230,230)',
                range=[-0.05, 1.05],
            ),
            camera=dict(
                up=dict(
                    x=0,
                    y=0,
                    z=1
                ),
                eye=dict(
                    x=-1.7428,
                    y=1.0707,
                    z=0.7100,
                )
            ),
            aspectratio = dict( x=1, y=1, z=0.7 ),
            aspectmode = 'manual',
        ),
    )

    fig = dict(data=datas, layout=layout)

    html = plotly.offline.plot(fig, auto_open=False, output_type="div", show_link=False, image_width=500, filename="scatter_plot", validate=False)



    #xs = []
    #ys = []
    #zs = []
    st = time.time()
    datas = []
    max_intersects = 0
    resolution = 10
    print("Check width: {}".format(1/resolution))
    total_intersections = 0
    all_intersection_values = []
    at_z = 0.0
    for _x in range(0, resolution):
        xs = []
        for _y in range(0, resolution):
            x = _x/resolution
            y = _y/resolution
            intersecting_events = 0
            for line in lines:
                x_i, x_f = line[0][0], line[0][1]
                y_i, y_f = line[1][0], line[1][1]
                z_i, z_f = line[2][0], line[2][1]
                if not (x_i == x_f and y_i == y_f): continue
                d = 1/resolution

                # Don't bother with exact collision detection for paths with couldn't possibly intersect box (~3x to ~10x speed gain)
                if ((x_i < x and x_f < x) or (x_i > x+d and x_f > x+d) or (y_i < y and y_f < y) or (y_i > y+d and y_f > y+d)):
                    continue

                p = Path(x_i, y_i, z_i, x_f, y_f, z_f)
                if path_passes_through_cube(p, x, y, at_z, d, d, d):
                    intersecting_events += 1


            #xs.append(x)
            #ys.append(y)
            #zs.append(intersecting_events)
            #if (resolution*0.2 < _x < resolution*0.8) and (resolution*0.2 < _y < resolution*0.8):
            all_intersection_values.append(intersecting_events)
            total_intersections += intersecting_events
            xs.append(intersecting_events)
            max_intersects = max(max_intersects, intersecting_events)
        datas.append(xs)

    print("Total intersecting events: {}".format(total_intersections))
    print("Intersection time: {}".format(time.time()-st))

    #for i in range(0, len(datas)):
    #    for j in range(0, len(datas[i])):
    #        datas[i][j] /= max_intersects

    #data = np.array((xs, ys, zs))
    data = [
        go.Surface(
            z=datas,
        )
    ]
    layout = go.Layout(
        title='Path density at z={}'.format(at_z),
        autosize=False,
        width=700,
        height=700,
        margin=dict(
            l=65,
            r=50,
            b=65,
            t=90
        ),
        scene = dict(
            zaxis = dict(
                range=[0, max_intersects]
            )
        )
    )
    fig = go.Figure(data=data, layout=layout)
    html2 = plotly.offline.plot(fig, auto_open=False, output_type="div", show_link=False, image_width=500, filename="scatter_plot", validate=False)

    trace = go.Scatter(
        x = list(range(0, len(all_intersection_values))),
        y = list(sorted(all_intersection_values))
    )
    layout = go.Layout(
        title='Intersection distribution',
        autosize=False,
        width=700,
        height=700,
    )
    fig = go.Figure(data=[trace,], layout=layout)
    html3 = plotly.offline.plot(fig, auto_open=False, output_type="div", show_link=False, image_width=500, filename="scatter_plot", validate=False)

    request_time = time.perf_counter()-start_time
    print("Request time: {}".format(request_time))
    kwargs = dict(
        charthtml=html,
        chartdensity=html2,
        total_events=len(lines),
        paths_shown=paths_shown,
        intersect_distribution=html3,
        request_time=request_time
    )
    return render_template("example_result.html", **kwargs)
