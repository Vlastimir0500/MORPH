module morph_uart_rx_candidate #(
    parameter integer CORRECTION_MODE = 0, // 0=fixed, 1=hard re-anchor, 2=bounded correction
    parameter integer MAX_PHASE_STEP = 4
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       rx,
    output logic [7:0] data_out,
    output logic       byte_valid,
    output logic       framing_error,
    output logic       sample_event_tick,
    output logic [3:0] sample_event_index
);
    localparam integer BIT_PERIOD = 40;
    localparam integer EARLY_DELAY = (BIT_PERIOD / 2) - 2;
    localparam integer NEXT_EARLY_DELAY = BIT_PERIOD - 4;

    localparam logic [3:0] IDLE         = 4'd0;
    localparam logic [3:0] START_EARLY  = 4'd1;
    localparam logic [3:0] START_CENTER = 4'd2;
    localparam logic [3:0] START_LATE   = 4'd3;
    localparam logic [3:0] DATA_EARLY   = 4'd4;
    localparam logic [3:0] DATA_CENTER  = 4'd5;
    localparam logic [3:0] DATA_LATE    = 4'd6;
    localparam logic [3:0] STOP_EARLY   = 4'd7;
    localparam logic [3:0] STOP_CENTER  = 4'd8;
    localparam logic [3:0] STOP_LATE    = 4'd9;

    logic [3:0] state;
    logic pin_prev;
    logic [15:0] timer;
    logic sample_early;
    logic sample_center;
    logic [2:0] bit_index;
    logic majority_value;

    always_comb begin
        majority_value = (sample_early & sample_center) |
                         (sample_early & rx) |
                         (sample_center & rx);
    end

    always_ff @(posedge clk) begin
        byte_valid        <= 1'b0;
        framing_error     <= 1'b0;
        sample_event_tick <= 1'b0;
        pin_prev          <= rx;

        if (!rst_n) begin
            state              <= IDLE;
            timer              <= 16'd0;
            sample_early       <= 1'b1;
            sample_center      <= 1'b1;
            bit_index          <= 3'd0;
            data_out           <= 8'd0;
            byte_valid         <= 1'b0;
            framing_error      <= 1'b0;
            sample_event_tick  <= 1'b0;
            sample_event_index <= 4'd0;
            pin_prev           <= rx;
        end else begin
            case (state)
                IDLE: begin
                    if (pin_prev && !rx) begin
                        state     <= START_EARLY;
                        timer     <= EARLY_DELAY;
                        data_out  <= 8'd0;
                        bit_index <= 3'd0;
                    end
                end

                START_EARLY, DATA_EARLY, STOP_EARLY: begin
                    if (timer <= 16'd1) begin
                        sample_early <= rx;
                        timer <= 16'd2;

                        if (state == START_EARLY)
                            state <= START_CENTER;
                        else if (state == DATA_EARLY)
                            state <= DATA_CENTER;
                        else
                            state <= STOP_CENTER;
                    end else if ((rx != pin_prev) && (CORRECTION_MODE != 0)) begin
                        if (CORRECTION_MODE == 1) begin
                            timer <= EARLY_DELAY;
                        end else begin
                            if (timer > (EARLY_DELAY + MAX_PHASE_STEP))
                                timer <= timer - MAX_PHASE_STEP;
                            else if ((timer + MAX_PHASE_STEP) < EARLY_DELAY)
                                timer <= timer + MAX_PHASE_STEP;
                            else
                                timer <= EARLY_DELAY;
                        end
                    end else begin
                        timer <= timer - 16'd1;
                    end
                end

                START_CENTER, DATA_CENTER, STOP_CENTER: begin
                    if (timer <= 16'd1) begin
                        sample_center <= rx;
                        timer <= 16'd2;

                        if (state == START_CENTER)
                            state <= START_LATE;
                        else if (state == DATA_CENTER)
                            state <= DATA_LATE;
                        else
                            state <= STOP_LATE;
                    end else begin
                        timer <= timer - 16'd1;
                    end
                end

                START_LATE: begin
                    if (timer <= 16'd1) begin
                        sample_event_tick  <= 1'b1;
                        sample_event_index <= 4'd0;

                        if (!majority_value) begin
                            state     <= DATA_EARLY;
                            timer     <= NEXT_EARLY_DELAY;
                            bit_index <= 3'd0;
                        end else begin
                            state <= IDLE; // Reject a false start.
                        end
                    end else begin
                        timer <= timer - 16'd1;
                    end
                end

                DATA_LATE: begin
                    if (timer <= 16'd1) begin
                        sample_event_tick  <= 1'b1;
                        sample_event_index <= {1'b0, bit_index} + 4'd1;
                        data_out[bit_index] <= majority_value;
                        timer <= NEXT_EARLY_DELAY;

                        if (bit_index == 3'd7) begin
                            state <= STOP_EARLY;
                        end else begin
                            bit_index <= bit_index + 3'd1;
                            state <= DATA_EARLY;
                        end
                    end else begin
                        timer <= timer - 16'd1;
                    end
                end

                STOP_LATE: begin
                    if (timer <= 16'd1) begin
                        sample_event_tick  <= 1'b1;
                        sample_event_index <= 4'd9;

                        if (majority_value)
                            byte_valid <= 1'b1;
                        else
                            framing_error <= 1'b1;

                        state <= IDLE;
                    end else begin
                        timer <= timer - 16'd1;
                    end
                end

                default: begin
                    state <= IDLE;
                    timer <= 16'd0;
                    framing_error <= 1'b1;
                end
            endcase
        end
    end
endmodule
